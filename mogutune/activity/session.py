# Copyright (c) 2026 Milkeyyy

"""Activity 用クイズセッション (UI 非依存・ブリッジ経由でイベントを配信する)

Discord の embed / ボタン UI を持たず、モグチューン Activity のプロトコルメッセージのみを
emit する。ゲームルールは全て mogutune_core を使用する (既存 QuizSession と同じ)。
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from contextlib import suppress
from os import getenv
from typing import TYPE_CHECKING, Literal

import discord
import mafic
from mogutune_core import answers, progression, ranking, trackpool
from mogutune_core.activity_protocol import (
	AnsweringMessage,
	AnswerResultMessage,
	BridgeUser,
	ErrorMessage,
	PlayerState,
	ProgressionState,
	QuestionStartMessage,
	QuizEndMessage,
	RankingEntry,
	ResumeMessage,
	StateMessage,
	TrackInfo,
)
from mogutune_core.models import is_same_track
from mogutune_core.progression import Action, Mode
from mogutune_core.roster import RemoveReason, Roster

from mogutune.client import client
from mogutune.quiz.manager import quiz_session_manager
from mogutune.quiz.track_adapter import to_core_track, to_core_tracks, to_mafic_tracks

if TYPE_CHECKING:
	from collections.abc import Awaitable, Callable

	from mogutune_core.activity_protocol import ClientMessage, ServerMessage, StartMessage
	from mogutune_core.models import Track

logger = logging.getLogger(__name__)

ANSWER_WINDOW_SECONDS = 5.0
"""解答択ウインドウ秒 (ボット仕様と同じ 5 秒)"""
START_BUFFER_MS = 1500.0
"""問題開始までのバッファ (start_at = 再生時刻 + 1.5s)"""
DISCONNECT_GRACE_SECONDS = 30.0
"""切断後のプレイヤー残留時間 (WS は切れやすいため)"""
MUSIC_VOLUME = int(getenv("MUSIC_VOLUME", "10"))
"""VC で再生する音量 (ボットの /play と同じ設定)"""


class NotInVoiceChannelError(Exception):
	"""Activity がボイスチャンネルから起動されていない"""


def now_ms() -> float:
	return time.time() * 1000


def _to_track_info(track: Track | None) -> TrackInfo | None:
	"""core.Track → protocol.TrackInfo (答え公開後にのみ使う)"""
	if track is None or track.uri is None:
		return None
	return TrackInfo(uri=track.uri, title=track.title, author=track.author, artwork_url=track.artwork_url)


class ActivitySession:
	"""1 ギルドの Activity クイズ進行 (既存 QuizSession とは排他で運用する)"""

	def __init__(
		self,
		guild_id: int,
		channel_id: int,
		instance_id: str,
		emit: Callable[[str, ServerMessage, int | None], Awaitable[None]],
	) -> None:
		self.guild_id = guild_id
		self.channel_id = channel_id
		self.instance_id = instance_id
		self.emit = emit
		self.roster = Roster()
		self.answer_state = answers.AnswerState()
		self.phase: Literal["lobby", "playing", "answered", "results"] = "lobby"
		self.mode = Mode.HOST
		self.rng = random.Random()  # noqa: S311 (core 注入用のゲーム乱数であり暗号用途ではない)
		self.q_pool: list[Track] = []
		"""出題プール (core.Track)"""
		self.q_tracks: list[mafic.Track] = []
		"""出題トラック (mafic.Track)"""
		self.q_count = 0
		self.q_number = 0
		self.current_track: mafic.Track | None = None
		self.revealed_track: mafic.Track | None = None
		self.profiles: dict[int, BridgeUser] = {}
		self.pl: mafic.Player | None = None
		self._inputs: asyncio.Queue[tuple[int, ClientMessage]] = asyncio.Queue()
		self._track_finished = asyncio.Event()
		self._play_failed = asyncio.Event()
		self._game_task: asyncio.Task | None = None
		self._answer_timer: asyncio.Task | None = None
		self._answer_deadline: float | None = None
		self._grace_tasks: dict[int, asyncio.Task] = {}
		self._closing = False

	# --- ブリッジからの入力 ---

	def handle(self, user_id: int, message: ClientMessage) -> None:
		"""クライアントメッセージを入力キューへ投入する (ノンブロッキング)"""
		self._inputs.put_nowait((user_id, message))

	def start(self) -> None:
		"""ゲームループを開始する (初回 join 時に呼ばれる)"""
		if self._game_task is None:
			self._game_task = asyncio.create_task(self.run())

	async def join(self, user: BridgeUser) -> None:
		self.profiles[user.id] = user
		grace = self._grace_tasks.pop(user.id, None)
		if grace is not None:
			grace.cancel()
		if not self.roster.is_joined(user.id):
			self.roster.add_player(user.id)
		await self._emit_state()

	async def leave(self, user_id: int) -> None:
		if user_id not in self.profiles or user_id in self._grace_tasks:
			return
		self._grace_tasks[user_id] = asyncio.create_task(self._expire_after_grace(user_id))
		await self._emit_state()

	async def request_state(self) -> None:
		"""再接続時などに現在の state を再配信する"""
		await self._emit_state()

	# --- メインループ ---

	async def run(self) -> None:
		"""ゲームループ: 開始待ち → クイズ進行 → 結果 → 再プレイ待ち"""
		self._game_task = asyncio.current_task()
		try:
			while not self._closing:
				while self.phase in ("lobby", "results"):
					user_id, message = await self._inputs.get()
					if message.type == "start" and await self._start_game(user_id, message):
						break
				if self._closing:
					break
				await self._play_quiz()
		finally:
			await self._cleanup()

	async def cancel(self) -> None:
		self._closing = True
		if self._game_task is not None:
			self._game_task.cancel()

	# --- ゲーム進行 ---

	async def _start_game(self, user_id: int, message: StartMessage) -> bool:  # noqa: PLR0911 (検証分岐が多い)
		"""ゲーム開始 (lobby / results からの start のみ受付)"""
		if message.mode is not Mode.HOST:
			await self._emit(ErrorMessage(key="activity.error.mode_not_available", params=[]), user_id=user_id)
			return False
		if self.roster.owner_id is None:
			self.roster.owner_id = user_id
		elif self.roster.owner_id != user_id:
			return False
		# 既存ボットの /play セッションとの排他
		if quiz_session_manager.get_session(self.guild_id) is not None:
			await self._emit(ErrorMessage(key="activity.error.already_started", params=[]), user_id=user_id)
			return False
		# VC へ接続
		if self.pl is None:
			try:
				self.pl = await self._connect_player()
			except NotInVoiceChannelError:
				await self._emit(ErrorMessage(key="activity.error.not_in_voice_channel", params=[]), user_id=user_id)
				return False
			except Exception:
				logger.exception("Activity VC 接続失敗 (guild=%s)", self.guild_id)
				await self._emit(ErrorMessage(key="activity.error.voice_join_failed", params=[]), user_id=user_id)
				return False
		# プレイリスト取得 (LavaSrc が Spotify 等を解決する。yt-dlp は使わない)
		try:
			tracks = await self.pl.fetch_tracks(message.query, mafic.SearchType.YOUTUBE_MUSIC)
		except Exception:
			logger.exception("トラック取得失敗 (guild=%s)", self.guild_id)
			await self._emit(ErrorMessage(key="activity.error.tracks_fetch_error", params=[]), user_id=user_id)
			return False
		if not tracks or not isinstance(tracks, mafic.Playlist) or not tracks.tracks:
			await self._emit(ErrorMessage(key="activity.error.no_tracks_found", params=[]), user_id=user_id)
			return False
		pool = trackpool.dedupe(to_core_tracks(tracks.tracks))
		if not pool:
			await self._emit(ErrorMessage(key="activity.error.no_tracks_found", params=[]), user_id=user_id)
			return False
		pool_error = trackpool.validate(len(pool), message.q_count)
		if pool_error is trackpool.PoolError.TOO_FEW_TRACKS:
			await self._emit(ErrorMessage(key="msg.q.init.must_be_at_least_two_songs", params=[]), user_id=user_id)
			return False
		if pool_error is trackpool.PoolError.NOT_ENOUGH_TRACKS:
			await self._emit(ErrorMessage(key="msg.q.init.not_enough_song", params=[len(pool), message.q_count]), user_id=user_id)
			return False
		self.q_pool = pool
		self.q_tracks = to_mafic_tracks(trackpool.sample_questions(pool, message.q_count, self.rng), tracks.tracks)
		self.q_count = message.q_count
		self.q_number = 0
		self.mode = message.mode
		for player in self.roster.players:
			player.reset()
		self.phase = "playing"
		await self._emit_state()
		return True

	async def _connect_player(self) -> mafic.Player:
		"""Activity のボイスチャンネルへ接続して mafic.Player を返す"""
		guild = client.get_guild(self.guild_id)
		if guild is None:
			raise NotInVoiceChannelError
		channel = guild.get_channel(self.channel_id)
		if channel is None:
			channel = await guild.fetch_channel(self.channel_id)
		if not isinstance(channel, discord.VoiceChannel):
			raise NotInVoiceChannelError
		if guild.voice_client is not None:
			await guild.voice_client.disconnect()
			await asyncio.sleep(2)
		return await channel.connect(cls=mafic.Player)

	async def _play_quiz(self) -> None:  # noqa: PLR0915 (進行フローは長い)
		"""問題を順に進行する。全問終了で結果フェーズへ"""
		while self.q_number < self.q_count:
			if self._closing:
				return
			track = self.q_tracks[self.q_number]
			self.q_number += 1
			self.current_track = track
			self.revealed_track = None
			self._answer_deadline = None
			self.answer_state = answers.AnswerState()
			self.answer_state.current_track_uri = track.uri
			self.phase = "playing"
			self._track_finished.clear()
			self._play_failed.clear()
			await self._emit_state()
			if self.pl is None:
				await self._skip_question(track)
				continue
			try:
				await self.pl.play(track, volume=MUSIC_VOLUME)
			except Exception as error:
				logger.warning("Activity 問題の再生に失敗、スキップ (guild=%s): %s", self.guild_id, error)
				await self._skip_question(track)
				continue
			self.answer_state.can_answer = True
			start_at = now_ms() + START_BUFFER_MS
			duration_ms = track.length
			await self._emit(
				QuestionStartMessage(
					q_number=self.q_number,
					start_at=start_at,
					duration_ms=duration_ms,
					deadline=start_at + duration_ms if duration_ms is not None else None,
				)
			)
			# 入力ループ (playing の間)
			while self.phase == "playing" and not self._closing:
				if self._play_failed.is_set():
					self._play_failed.clear()
					await self._skip_question(track)
					break
				get_task = asyncio.ensure_future(self._inputs.get())
				finished_waiter = asyncio.ensure_future(self._track_finished.wait())
				failed_waiter = asyncio.ensure_future(self._play_failed.wait())
				try:
					_done, _ = await asyncio.wait(
						{get_task, finished_waiter, failed_waiter},
						return_when=asyncio.FIRST_COMPLETED,
					)
					if self._track_finished.is_set():
						# 曲フル再生で自動スキップ (答えは公開しない)
						self._track_finished.clear()
						if get_task.done():
							self._inputs.put_nowait(get_task.result())
						else:
							get_task.cancel()
						break
					if self._play_failed.is_set():
						if get_task.done():
							self._inputs.put_nowait(get_task.result())
						else:
							get_task.cancel()
						continue  # 次のループでスキップ処理
					user_id, message = get_task.result()
					await self._handle_input(user_id, message)
				finally:
					if not finished_waiter.done():
						finished_waiter.cancel()
					if not failed_waiter.done():
						failed_waiter.cancel()
			# answered フェーズ: 主催者の進行を待つ
			if self.phase == "answered" and not self._closing:
				action = await self._wait_advance()
				if action is Action.END:
					await self._finish()
					return
				# NEXT / SKIP → 次の問題へ
				continue
		await self._finish()

	async def _skip_question(self, track: mafic.Track) -> None:
		"""再生失敗時: 答えを公開してこの問題をスキップ"""
		self.revealed_track = track
		self.answer_state = answers.AnswerState()
		self.answer_state.current_track_uri = track.uri
		await self._emit(ErrorMessage(key="activity.error.playback_failed", params=[]))
		await self._emit_state()
		await asyncio.sleep(1.0)

	async def _handle_input(self, user_id: int, message: ClientMessage) -> None:
		if message.type == "raise_hand":
			await self._raise_hand(user_id)
		elif message.type == "answer":
			await self._answer(user_id, message.uri)
		# advance / start / vote / ping は playing 中は無視

	async def _raise_hand(self, user_id: int) -> None:
		"""早押し (サーバー受信時刻の先着を core が判定)"""
		if self.current_track is None or self.pl is None:
			return
		result = answers.check_raise_hand(self.answer_state, self.roster, user_id)
		if isinstance(result, answers.RaiseHandError):
			await self._send_raise_hand_error(user_id, result)
			await self._emit_state()
			return
		self.answer_state.answering_player_id = result.id
		deadline = now_ms() + ANSWER_WINDOW_SECONDS * 1000
		self._answer_deadline = deadline
		# ボットと同じく全プレイヤーの不正解フラグをリセット (session.py の refresh)
		answers.refresh_misses(self.roster)
		choices = answers.generate_choices(to_core_track(self.current_track), self.q_pool, self.rng)
		await self.pl.pause()
		await self._emit(
			AnsweringMessage(
				user_id=result.id,
				deadline=deadline,
				choices=[choice for choice in (_to_track_info(t) for t in choices) if choice is not None],
			)
		)
		await self._emit_state()
		self._set_answer_timer(asyncio.create_task(self._answer_timeout(result.id, deadline)))

	async def _send_raise_hand_error(self, user_id: int, error: answers.RaiseHandError) -> None:
		keys = {
			answers.RaiseHandError.NOT_PLAYING: ("activity.error.not_playing", []),
			answers.RaiseHandError.ALREADY_ANSWERING: ("msg.q.answering.already.description", []),
			answers.RaiseHandError.CANNOT_ANSWER: ("view.q.answer_button.cannot_answered", []),
			answers.RaiseHandError.NOT_JOINED: ("view.q.answer_button.not_joined", []),
			answers.RaiseHandError.MISS: ("view.q.answer_button.miss", []),
		}
		key, params = keys[error]
		await self._emit(ErrorMessage(key=key, params=params), user_id=user_id)

	async def _answer_timeout(self, user_id: int, deadline: float) -> None:
		"""解答ウィンドウ満了 → 不正解 (ボット session.py の 5 秒タイムアウトと同じ)"""
		wait = deadline - now_ms()
		if wait > 0:
			await asyncio.sleep(wait / 1000)
		if self.answer_state.answering_player_id != user_id or self.phase != "playing":
			return
		await self._incorrect(user_id)

	async def _answer(self, user_id: int, uri: str) -> None:
		"""5択の解答"""
		if self.answer_state.answering_player_id != user_id or self.current_track is None:
			return
		if answers.is_correct(uri, self.current_track.uri):
			await self._correct(user_id)
		else:
			await self._incorrect(user_id)

	async def _correct(self, user_id: int) -> None:
		"""正解: 答えを公開して answered フェーズへ"""
		self._cancel_answer_timer()
		self._answer_deadline = None
		player = self.roster.get(user_id)
		if player is None:
			return
		player.correct()
		self.answer_state = answers.AnswerState()
		self.answer_state.current_track_uri = self.current_track.uri if self.current_track is not None else None
		self.revealed_track = self.current_track
		self.phase = "answered"
		if self.pl is not None:
			await self.pl.stop()
		for uid in list(self.profiles):
			await self._emit(
				AnswerResultMessage(
					user_id=user_id,
					correct=True,
					track=_to_track_info(self.current_track) or TrackInfo(uri="", title="", author=""),
					progression=self._progression(uid),
				),
				user_id=uid,
			)
		await self._emit_state()

	async def _incorrect(self, user_id: int) -> None:
		"""不正解: お手つきを付けて再生を再開"""
		player = self.roster.get(user_id)
		if player is None:
			return
		player.incorrect()
		self.answer_state.answering_player_id = None
		self._answer_deadline = None
		if self.pl is not None:
			await self.pl.resume()
		await self._emit(ResumeMessage(resume_at=now_ms()))
		await self._emit_state()

	async def _wait_advance(self) -> Action:
		"""主催者による進行操作を待つ (answered フェーズのみ)"""
		while True:
			user_id, message = await self._inputs.get()
			if message.type == "advance" and progression.HostProgression.can_advance(message.action, user_id, self.roster.owner_id):
				return message.action

	async def _finish(self) -> None:
		"""全問題終了: ランキングを公開して results フェーズへ"""
		self._cancel_answer_timer()
		self._answer_deadline = None
		self.current_track = None
		self.revealed_track = None
		self.answer_state = answers.AnswerState()
		self.phase = "results"
		entries = ranking.build_ranking(self.roster.players)
		await self._emit(QuizEndMessage(ranking=[RankingEntry(rank=e.rank, user_id=e.player_id, point=e.point) for e in entries]))
		await self._emit_state()

	# --- mafic イベント ---

	def on_track_finished(self, track: mafic.Track) -> None:
		"""TrackEnd (FINISHED): 曲フル再生で次の問題へ"""
		if self.phase != "playing" or not is_same_track(self.current_track, track):
			return
		self._track_finished.set()

	def on_track_exception(self, track: mafic.Track) -> None:
		"""TrackException: 再生失敗 → この問題をスキップ"""
		if self.phase != "playing" or self.answer_state.answering_player_id is not None:
			return
		if not is_same_track(self.current_track, track):
			return
		logger.warning("Activity 問題の再生例外でスキップ (guild=%s): %s", self.guild_id, track.title)
		self._play_failed.set()

	# --- 切断猶予 ---

	async def _expire_after_grace(self, user_id: int) -> None:
		await asyncio.sleep(DISCONNECT_GRACE_SECONDS)
		if self._grace_tasks.pop(user_id, None) is None:
			return
		self.profiles.pop(user_id, None)
		result = self.roster.remove_player(user_id)
		await self._emit_state()
		if result in (RemoveReason.NO_PLAYERS_LEFT, RemoveReason.OWNER_LEFT):
			logger.info("Activity セッション終了 (guild=%s): %s", self.guild_id, result.value)
			from mogutune.activity.manager import activity_manager  # noqa: PLC0415 (循環 import 回避)

			await activity_manager.end_session(self.guild_id)

	# --- state スナップショット ---

	def _progression(self, user_id: int) -> ProgressionState:
		is_owner = self.roster.owner_id is not None and user_id == self.roster.owner_id
		can_advance = self.phase == "answered" and is_owner
		return ProgressionState(next=can_advance, skip=can_advance, end=can_advance)

	def build_state(self, user_id: int) -> StateMessage:
		players: list[PlayerState] = []
		for player in self.roster.players:
			profile = self.profiles.get(player.id)
			players.append(
				PlayerState(
					id=player.id,
					username=profile.username if profile is not None else str(player.id),
					avatar=profile.avatar if profile is not None else "",
					point=player.point,
					miss=player.miss,
					answering=self.answer_state.answering_player_id == player.id,
				)
			)
		revealed = to_core_track(self.revealed_track) if self.revealed_track is not None else None
		return StateMessage(
			phase=self.phase,
			mode=self.mode.value,
			owner_id=self.roster.owner_id,
			players=players,
			q_number=self.q_number,
			q_count=self.q_count,
			current_answerer=self.answer_state.answering_player_id,
			answer_deadline=self._answer_deadline,
			revealed_track=_to_track_info(revealed),
			progression=self._progression(user_id),
		)

	# --- 配信ヘルパー ---

	async def _emit(self, message: ServerMessage, user_id: int | None = None) -> None:
		await self.emit(self.instance_id, message, user_id)

	async def _emit_state(self) -> None:
		for uid in list(self.profiles):
			await self._emit(self.build_state(uid), user_id=uid)

	# --- タイマー管理 ---

	def _set_answer_timer(self, task: asyncio.Task) -> None:
		self._cancel_answer_timer()
		self._answer_timer = task

	def _cancel_answer_timer(self) -> None:
		task = self._answer_timer
		if task is not None and task is not asyncio.current_task():
			task.cancel()
		self._answer_timer = None

	# --- クリーンアップ ---

	async def _cleanup(self) -> None:
		self._cancel_answer_timer()
		for task in self._grace_tasks.values():
			task.cancel()
		self._grace_tasks.clear()
		if self.pl is not None:
			with suppress(Exception):
				await self.pl.stop()
			with suppress(Exception):
				await self.pl.disconnect()
		self.pl = None
		from mogutune.activity.manager import activity_manager  # noqa: PLC0415 (循環 import 回避)

		activity_manager.forget(self.guild_id, self.instance_id)
		logger.info("Activity セッション破棄 (guild=%s)", self.guild_id)
