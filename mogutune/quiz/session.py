import asyncio
import datetime
import logging
import random
import traceback
from dataclasses import dataclass, field
from os import getenv

import discord
import mafic
from mogutune_core import answers, ranking, trackpool
from mogutune_core.models import is_same_track
from mogutune_core.roster import RemoveReason, Roster
from pycord.localizer import t

from mogutune.client import client
from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.quiz.player import QuizPlayer
from mogutune.quiz.track_adapter import to_core_track, to_core_tracks, to_mafic_tracks
from mogutune.sfx import SFX

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@dataclass
class QuizSession:
	"""クイズのセッション"""

	guild_id: int
	"""クイズが実行されているサーバーのID"""
	channel_id: int
	"""クイズが実行されているボイスチャンネルのID"""

	pl: mafic.Player
	"""プレイヤー (Mafic)"""

	query: str
	"""プレイリストのURL"""

	PL_VOLUME: int = int(getenv("MUSIC_VOLUME", "10"))
	"""プレイヤーで再生する音楽の音量"""

	PL_SFX_VOLUME: int = int(getenv("SFX_VOLUME", "10"))
	"""プレイヤーで再生するSFXの音量"""

	roster: Roster = field(default_factory=Roster)
	"""参加者 (プレイヤー一覧・参加待ちキュー・主催者) の管理"""
	playing: bool = False
	"""クイズが開始されているかどうか"""

	rng: random.Random = field(default_factory=random.Random)
	"""乱数生成器 (core へ注入する)"""

	owner: QuizPlayer | None = None
	"""クイズの主催者"""

	answering_player: QuizPlayer | None = None
	"""現在解答中のプレイヤー"""
	current_q_number: int = 0
	"""問題番号"""
	q_start_time: datetime.datetime | None = None
	"""問題開始時刻"""
	DEFAULT_Q_WAIT_SECONDS: int = 1
	q_wait_seconds: int = 1
	"""問題開始待ち時間 (秒)"""

	q_original_tracks: list[mafic.Track] | None = None
	"""問題の元のトラック一覧"""
	q_tracks: list[mafic.Track] | None = None
	"""問題のトラック一覧"""
	q_tracks_count: int = 0
	"""問題のトラック数"""
	current_q_track: mafic.Track | None = None
	"""現在出題しようとしているトラック"""
	is_skipping_current_q_by_exception: bool = False
	"""現在の問題を再生例外によってスキップ中かどうか"""

	next_cleanup_messages: list[discord.Message | discord.WebhookMessage] = field(default_factory=list)
	"""次の問題開始時に削除するメッセージのリスト"""

	q_msg: discord.Message | None = None
	"""解答ボタンなどがくっついているメッセージ"""

	can_answered: bool = False
	"""解答ができる状態かどうか"""

	NEXT: asyncio.Event = field(default_factory=asyncio.Event)
	ANSWERED: asyncio.Event = field(default_factory=asyncio.Event)
	SFX_FINISHED: asyncio.Event = field(default_factory=asyncio.Event)
	"""SFX再生完了イベント"""

	is_playing_sfx: bool = False
	"""SFXを再生しているかどうか"""
	restore_track_after_sfx: bool = True
	"""SFX再生後に元のトラックを復帰するかどうか"""
	original_track_before_sfx: mafic.Track | None = None
	"""SFX再生前のトラック"""
	original_position_before_sfx: int = 0
	"""SFX再生前の再生位置"""
	was_playing_before_sfx: bool = False
	"""SFX再生前に再生中だったかどうか"""
	PLAYBACK_EXCEPTION_NOTICE_SECONDS: int = 4
	"""再生例外で問題をスキップする際の通知表示時間"""
	RESUME_SEEK_BACK_MS: int = 3000
	"""回答後の再生再開時に巻き戻す時間 (ミリ秒)"""
	RESUME_SEEK_MIN_POSITION_MS: int = 4000
	"""巻き戻しを適用する回答開始時再生位置の下限 (ミリ秒) 未満の場合は最初から再生する"""
	answer_pause_position: int = 0
	"""回答開始時に一時停止した再生位置 (ミリ秒)"""

	async def add_player(self, user_id: int) -> None:
		"""プレイヤーを追加"""
		if self.roster.is_joined(user_id):
			return
		logger.debug(f"プレイヤー追加: {user_id}")
		self.roster.add_player(user_id)

	async def remove_player(self, user_id: int) -> RemoveReason:
		"""プレイヤーを削除する

		終了処理は呼び出し側が RemoveReason を見て行う
		"""
		logger.debug(f"プレイヤー削除: {user_id}")
		return self.roster.remove_player(user_id)

	async def add_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを追加"""
		if user_id in self.roster.queue:
			return
		logger.debug(f"参加待ちプレイヤー追加: {user_id}")
		self.roster.add_queue(user_id)

	async def remove_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを削除"""
		if user_id not in self.roster.queue:
			return
		logger.debug(f"参加待ちプレイヤー削除: {user_id}")
		self.roster.remove_queue(user_id)

	async def join_queued_players(self) -> None:
		"""参加待ちのプレイヤー全員を参加させる"""
		logger.debug("参加待ちプレイヤー参加")
		self.roster.join_queued_players()

	def is_player_joined(self, user_id: int) -> bool:
		"""プレイヤーが参加しているかどうかを返す"""
		return self.roster.is_joined(user_id)

	async def join_player(self, user_id: int) -> None:
		"""プレイヤーを参加させる

		既にクイズが開始されている場合は順番待ちに追加する
		"""
		if not self.roster.is_joined(user_id):
			if self.playing:
				await self.add_queue(user_id)
			else:
				await self.add_player(user_id)

	async def get_player(self, user_id: int) -> QuizPlayer | None:
		"""プレイヤーを取得"""
		return self.roster.get(user_id)

	async def get_answer_tracks(self) -> list[mafic.Track]:
		"""解答候補のトラック一覧を生成"""
		if self.q_original_tracks is None:
			return []
		if self.q_tracks is None:
			return []
		if self.pl is None:
			return []
		if self.pl.current is None:
			return []

		# 正解の曲を除いてダミーの選択肢を4つサンプリングし、正解を足してシャッフルする
		choices = answers.generate_choices(to_core_track(self.pl.current), to_core_tracks(self.q_original_tracks), self.rng)
		# core.Track を URI で元の mafic.Track へ引き戻す
		return to_mafic_tracks(choices, self.q_original_tracks)

	def get_current_track(self) -> mafic.Track | None:
		"""再生中の楽曲を取得する"""
		if self.pl is None:
			return None
		return self.pl.current

	def get_track_from_uri(self, uri: str) -> mafic.Track | None:
		"""URIからトラックを取得する"""
		if self.q_original_tracks is None:
			return None
		for track in self.q_original_tracks:
			if track.uri == uri:
				return track
		return None

	@staticmethod
	def format_track_title(track: mafic.Track | None, max_length: int | None = None) -> str:
		"""表示用の楽曲タイトルを返す"""
		if track is None:
			return "Unknown"

		title = track.title if track.source == "youtube" else track.title + " - " + track.author
		if max_length is not None and len(title) > max_length:
			return title[:max_length] + "..."
		return title

	@staticmethod
	def set_track_artwork(embed: discord.Embed, track: mafic.Track | None) -> discord.Embed:
		"""トラックのジャケット画像を埋め込みへ設定する"""
		if track is not None and track.artwork_url is not None:
			embed.set_image(url=track.artwork_url)
		return embed

	@staticmethod
	def set_footer_track_info(embed: discord.Embed, track: mafic.Track | None) -> discord.Embed:
		"""トラックの追加情報を埋め込みのフッターへ設定する"""
		if track is not None:
			text = ""
			if track.isrc is not None:
				text += f"ISRC: {track.isrc}\n"
			text += f"Author: {track.author}\nSource: {track.source}"
			embed.set_footer(text=text)
		return embed

	def _question_embed(self) -> discord.Embed:
		"""問題表示用の埋め込みを生成する"""
		return EmbedsTemplates.info(
			title=t("msg.q.start.title", str(self.current_q_number)),
			description=t("msg.q.start.description"),
			icon="❔",
		)

	async def _edit_q_msg(self, embed: discord.Embed) -> None:
		"""q_msg の埋め込みを編集する (存在しない場合は無視)"""
		if self.q_msg is None:
			return
		try:
			await self.q_msg.edit(embed=embed)
		except discord.errors.NotFound:
			pass

	def is_question_track_exception_target(self, track: mafic.Track) -> bool:
		"""現在の出題トラックに対する再生例外かどうかを返す"""
		if not self.playing:
			return False
		if self.is_playing_sfx:
			return False
		if not self.can_answered:
			return False
		if self.answering_player is not None:
			return False
		if self.is_skipping_current_q_by_exception:
			return False
		return is_same_track(self.current_q_track, track)

	def clear_current_q_track_state(self) -> None:
		"""現在の出題トラックに関する状態をリセットする"""
		self.current_q_track = None
		self.is_skipping_current_q_by_exception = False

	async def skip_current_q_by_track_exception(self, track: mafic.Track) -> None:
		"""出題トラックの再生例外時に現在の問題をスキップする"""
		if self.is_skipping_current_q_by_exception:
			return

		self.is_skipping_current_q_by_exception = True
		self.can_answered = False
		self.answering_player = None
		self.refresh()
		self.q_wait_seconds = 0

		try:
			if self.voice_channel is not None:
				_embed = self.set_track_artwork(
					EmbedsTemplates.warning(
						title=t("msg.q.playback_exception_skip.title"),
						description=t("msg.q.playback_exception_skip.description", self.format_track_title(track), track.uri or self.query),
						icon="⚠️",
					),
					track,
				)
				msg = await self.voice_channel.send(embed=_embed)
				self.next_cleanup_messages.append(msg)
			if self.playing:
				await self.play_sfx(SFX.ERROR, restore=False)
				await asyncio.sleep(self.PLAYBACK_EXCEPTION_NOTICE_SECONDS)
		finally:
			self.NEXT.set()

	def refresh(self) -> None:
		"""全プレイヤーの不正解フラグをリセット"""
		answers.refresh_misses(self.roster)

	def reset(self) -> None:
		"""クイズセッションをリセット"""
		# 全プレイヤーのポイントと不正解フラグをリセット
		[player.reset() for player in self.roster.players]
		# 各変数をリセット
		self.q_original_tracks = []
		self.q_tracks = []
		self.q_tracks_count = 0
		self.clear_current_q_track_state()
		self.current_q_number = 0
		self.q_start_time = None
		self.q_wait_seconds = self.DEFAULT_Q_WAIT_SECONDS
		self.can_answered = False
		self.answering_player = None
		self.next_cleanup_messages = []
		self.q_msg = None
		self.owner = None
		self.roster.owner_id = None
		self.restore_track_after_sfx = True
		self.answer_pause_position = 0

	async def play_sfx(self, sfx_query: str | SFX, restore: bool = True) -> None:
		"""SFXを再生する

		再生中の楽曲を一時停止し、SFXを再生する
		"""
		if self.is_playing_sfx:
			logger.warning("SFX再生中止 - 既に別のSFXを再生中です")
			return

		if isinstance(sfx_query, SFX) and sfx_query.value is None:
			logger.warning(f"SFX再生中止 - SFX の URL またはファイルパスが設定されていません (SFX.{sfx_query.name})")
			return

		# 解答可能かどうかを記憶
		before_can_answered = self.can_answered
		# 解答できない状態にする
		self.can_answered = False

		try:
			self.is_playing_sfx = True
			self.restore_track_after_sfx = restore
			self.SFX_FINISHED.clear()

			# 元のトラックと再生位置を保存
			self.original_track_before_sfx = self.pl.current
			if self.original_track_before_sfx:
				self.original_position_before_sfx = self.pl.position
				# 再生中だったかどうかを保存 (paused が False かつ current がある場合)
				self.was_playing_before_sfx = not self.pl.paused
			else:
				self.original_position_before_sfx = 0
				self.was_playing_before_sfx = False

			# 再生を一時停止
			await self.pl.pause()

			# SFXを検索して再生
			track: mafic.Track | str | None = None
			# URL
			if isinstance(sfx_query, str):
				if sfx_query.startswith(("http://", "https://")):
					sfx_tracks = await self.pl.fetch_tracks(sfx_query)
					if not sfx_tracks or not isinstance(sfx_tracks, list):
						raise Exception("SFX track not found or is a playlist.")
					track = sfx_tracks[0]
				# ローカルファイルパス
				else:
					track = sfx_query
			else:
				# 環境変数で設定された値 (SFX Enum)
				track = str(sfx_query.value)

			# SFXを再生
			await self.pl.play(track, volume=self.PL_SFX_VOLUME)

			# SFXの再生終了を待つ
			await self.SFX_FINISHED.wait()

		except Exception:
			logger.error("SFXの再生に失敗しました。")
			logger.error(traceback.format_exc())
			# エラーが発生した場合は元の楽曲の再生を再開する
			if restore and self.original_track_before_sfx:
				try:
					await self.pl.play(
						self.original_track_before_sfx,
						start_time=self.original_position_before_sfx,
						volume=self.PL_VOLUME,
					)
				except Exception:
					logger.error("元の楽曲の復帰に失敗しました。")
					logger.error(traceback.format_exc())

		finally:
			self.is_playing_sfx = False
			self.restore_track_after_sfx = True
			# SFX再生前が解答できる状態だった場合は解答できる状態に戻す
			if restore and before_can_answered:
				self.can_answered = True

	async def resolve_youtube_track_uri(self, track: mafic.Track) -> str | None:
		"""トラックのYouTube URLを解決する"""
		if track.source == "youtube":
			return track.uri

		# ISRC を取得してみる
		_isrc = getattr(track, "isrc", None)

		# ISRC がない場合は plugin_info から探してみる
		if _isrc is None and hasattr(track, "plugin_info") and track.plugin_info:
			_isrc = track.plugin_info.get("isrc")

		logger.info(f"Searching YouTube for: {track.author} - {track.title} (ISRC: {_isrc})")
		try:
			if _isrc:
				_search_results = await self.pl.fetch_tracks(f'"{_isrc}"', mafic.SearchType.YOUTUBE_MUSIC)
			else:
				_search_results = await self.pl.fetch_tracks(f"{track.author} - {track.title}", mafic.SearchType.YOUTUBE)
			if _search_results and isinstance(_search_results, list) and len(_search_results) > 0:
				_uri = _search_results[0].uri
				logger.info(f"Found YouTube track (ISRC): {_uri}")
				return _uri
			# ISRC で見つからなかった場合はタイトルで再検索
			if _isrc:
				logger.warning("YouTube track not found via ISRC. Retrying with title...")
				_search_results = await self.pl.fetch_tracks(f"{track.author} - {track.title}", mafic.SearchType.YOUTUBE)
				if _search_results and isinstance(_search_results, list) and len(_search_results) > 0:
					_uri = _search_results[0].uri
					logger.info(f"Found YouTube track (Title): {_uri}")
					return _uri
				logger.warning("YouTube track not found via title search.")
			else:
				logger.warning("YouTube track not found via search.")
		except Exception:
			logger.error("Failed to search YouTube track.")
			logger.error(traceback.format_exc())

		return None

	async def end(self) -> None:
		"""クイズを終了する"""
		self.playing = False
		try:
			await self.pl.stop()
		except Exception:
			logger.error("- 再生終了エラー")
			logger.error(traceback.format_exc())

		# 待機状態を解除してループを回す
		self.NEXT.set()

	async def play(self, tracks: mafic.Playlist, q_count: int, owner_id: int, query: str) -> bool | str:
		"""クイズを開始する"""
		from mogutune.quiz.views import QuizAnswerButtonView, QuizReplayButtonView  # noqa: PLC0415

		try:
			self.playing = True
			self.reset()

			self.guild = client.get_guild(self.guild_id)  # fetch
			if self.guild is None:
				return await DebugLogger.report_internal_error("クイズ開始処理失敗: Guild not found")
			self.voice_channel = self.guild.get_channel(self.channel_id)
			if self.voice_channel is None:
				return await DebugLogger.report_internal_error("クイズ開始処理失敗: Voice Channel not found")
			if not isinstance(self.voice_channel, discord.VoiceChannel):
				return await DebugLogger.report_internal_error("クイズ開始処理失敗: Channel is not Voice Channel")

			# クイズの主催者を設定
			self.owner = await self.get_player(owner_id)
			self.roster.owner_id = owner_id

			# トラック一覧
			self.q_original_tracks = tracks.tracks
			# 重複したトラックを除く (core で判定し、URI で mafic.Track へ引き戻す)
			unique_core_tracks = trackpool.dedupe(to_core_tracks(self.q_original_tracks))
			self.q_original_tracks = to_mafic_tracks(unique_core_tracks, self.q_original_tracks)

			# 出題プールの検証
			pool_error = trackpool.validate(len(self.q_original_tracks), q_count)

			# 楽曲数が2曲未満の場合はエラーメッセージを返す
			if pool_error is trackpool.PoolError.TOO_FEW_TRACKS:
				await self.voice_channel.send(embed=EmbedsTemplates.error(description=t("msg.q.init.must_be_at_least_two_songs")))
				# 終了
				self.playing = False
				self.reset()
				return False

			# 有効なトラック数が問題数 (および選択肢生成に必要な最小数) よりも少ない場合はエラーメッセージを返す
			if pool_error is trackpool.PoolError.NOT_ENOUGH_TRACKS:
				await self.voice_channel.send(
					embed=EmbedsTemplates.error(description=t("msg.q.init.not_enough_song", len(self.q_original_tracks), q_count))
				)
				# 終了
				self.playing = False
				self.reset()
				return False

			# トラック一覧から指定された数だけランダムに取り出す (問題の生成)
			core_questions = trackpool.sample_questions(to_core_tracks(self.q_original_tracks), q_count, self.rng)
			self.q_tracks = to_mafic_tracks(core_questions, self.q_original_tracks)
			self.q_tracks_count = q_count

			logger.debug(f"クイズ開始: {self.guild_id}/{self.channel_id}")

			logger.debug("- プレイヤー一覧生成")
			# プレイヤー一覧テキストを生成
			player_mentions = []
			for p in self.roster.players:
				member: discord.Member | None = await self.guild.get_or_fetch(discord.Member, p.id)
				if member is not None:
					if member.mention:
						player_mentions.append(member.mention)
					else:
						player_mentions.append(member.display_name)
			player_list_text = "  - " + "\n  - ".join(player_mentions)

			logger.debug("Tracks Plugin Info")
			logger.debug(tracks.plugin_info)

			# 表示するプレイリスト (アルバム) のタイトルの種類とジャケットを設定する
			playlist_title_prefix = t("msg.q.init.description.playlist_type.playlist")
			artwork_url = None
			if tracks.plugin_info is not None:
				# Spotify
				if tracks.tracks[0].source == "spotify":
					# アルバム
					if tracks.plugin_info.get("type") == "album":
						playlist_title_prefix = t("msg.q.init.description.playlist_type.album")
					# ジャケットを取得
					artwork_url = tracks.plugin_info.get("artworkUrl")

			# 表示するプレイリスト名のテキストを生成 (URLも挿入)
			playlist_title = playlist_title_prefix + ": [**" + tracks.name + "**](" + query + ")"

			# 埋め込みメッセージを生成
			start_msg_embed = EmbedsTemplates.info(
				title=t("msg.q.init.title"),
				description=t("msg.q.init.description", playlist_title, q_count, player_list_text),
				icon="▶️",
			)
			# ジャケットを設定
			start_msg_embed.set_thumbnail(url=artwork_url)

			# クイズ開始メッセージを送信
			start_msg = await self.voice_channel.send(embed=start_msg_embed)
			# 問題開始メッセージを送信
			q_msg = await self.voice_channel.send(
				embed=EmbedsTemplates.info(title=t("msg.q.start.title", "-"), description=t("msg.q.start.description"), icon="❔"),
				view=QuizAnswerButtonView(self.guild_id),  # 回答ボタン
			)
			self.q_msg = q_msg

			for i, q in enumerate(self.q_tracks, 1):
				if not self.playing:
					break

				logger.debug(f"{i}問目")

				self.current_q_number = i
				self.current_q_track = q
				self.is_skipping_current_q_by_exception = False

				# 参加待ちのプレイヤーを参加させる
				await self.join_queued_players()

				# プレイヤー一覧テキストを更新する
				logger.debug("- プレイヤー一覧更新")
				player_mentions = []
				for p in self.roster.players:
					member = await self.guild.get_or_fetch(discord.Member, p.id)
					if member is not None:
						if member.mention:
							player_mentions.append(member.mention)
						else:
							player_mentions.append(member.display_name)
				player_list_text = "  - " + "\n  - ".join(player_mentions)
				start_msg.embeds[0].description = t("msg.q.init.description", playlist_title, q_count, player_list_text)
				await start_msg.edit(embed=start_msg.embeds[0])

				self.NEXT.clear()

				logger.debug("- タイトル更新")
				# タイトルを更新
				await q_msg.edit(embed=self._question_embed())

				# SFX
				await self.play_sfx(SFX.Q)

				# 問題開始時刻を更新
				self.q_start_time = datetime.datetime.now(tz=datetime.UTC)

				# 解答ができる状態にする
				self.can_answered = True

				logger.debug("- 再生開始")

				# 再生
				await self.pl.play(q, volume=self.PL_VOLUME)
				await self.NEXT.wait()  # 待機
				if not self.is_skipping_current_q_by_exception:
					await self.pl.pause()  # 念の為一時停止

				# 解答ができない状態にする
				self.can_answered = False
				# 解答者をリセット
				self.answering_player = None
				# 全プレイヤーの不正解フラグをリセット
				self.refresh()
				self.clear_current_q_track_state()

				logger.debug("- 再生終了")

				# 削除対象のメッセージたちを削除する
				for msg in self.next_cleanup_messages:
					try:
						await msg.delete()
						logger.debug(f"- 問題終了時メッセージ削除: {msg.id}")
					except discord.errors.NotFound:
						logger.debug(f"- 問題終了時メッセージ削除失敗 - NotFound: {msg.id}")
					except Exception:
						logger.error("- 問題終了時メッセージクリーンアップエラー")
						logger.error(traceback.format_exc())
						await DebugLogger.report_internal_error(traceback.format_exc())
				# 削除対象のメッセージ一覧をリセットする
				self.next_cleanup_messages = []

				# 待機
				logger.debug("待機")
				if not self.playing:
					break
				await asyncio.sleep(self.q_wait_seconds)
				# 待機時間をリセット
				self.q_wait_seconds = self.DEFAULT_Q_WAIT_SECONDS

			# 解答メッセージを削除
			try:
				await q_msg.delete()
			except discord.errors.NotFound:
				pass

			try:
				logger.debug("ランキング生成")
				# ランキングテキストを生成
				if len(self.roster.players) == 0:  # プレイヤーが0人の場合は専用のメッセージを設定
					ranking_list = [t("msg.q.end.no_players")]
				else:
					ranking_list = []
					# ポイント順にソート (同点同順)
					for entry in ranking.build_ranking(self.roster.players):
						member = await self.guild.get_or_fetch(discord.Member, entry.player_id)
						pn = "Unknown"
						if member is not None:
							pn = member.mention or member.display_name

						rank_icon = f"**{entry.rank}**"
						if entry.rank == 1:
							rank_icon = "🥇"
						elif entry.rank == 2:
							rank_icon = "🥈"
						elif entry.rank == 3:
							rank_icon = "🥉"

						pt = t("cmd.play.ranking.point") if entry.point == 1 else t("cmd.play.ranking.points")
						ranking_list.append(f"{rank_icon} {pn}: **`{entry.point}`** {pt}")
				# 結合
				ranking_text = "\n".join(ranking_list)

				# 終了メッセージを送信する
				await self.voice_channel.send(
					embed=EmbedsTemplates.info(title=t("msg.q.end.title"), description=t("msg.q.end.description", ranking_text), icon="🏁"),
					view=QuizReplayButtonView(self.query, q_count),  # 再度プレイボタン
				)
			except Exception:
				logger.error("- 終了メッセージ送信/ランキング生成エラー")
				logger.error(traceback.format_exc())

			logger.debug("クイズ終了")
			# 終了
			self.reset()
			# await self.end()
			return True
		except Exception:
			return await DebugLogger.report_internal_error(traceback.format_exc())

	async def raise_hand(self, interaction: discord.Interaction, user_id: int) -> None:
		"""再生を一時停止して解答の選択肢を送信する"""
		from mogutune.quiz.views import QuizAnswerSelectView  # noqa: PLC0415

		# 解答までにかかった時間と時刻を計算
		answer_dt = datetime.datetime.now(tz=datetime.UTC)
		answer_time_sec = -1 if self.q_start_time is None else f"{(answer_dt - self.q_start_time).total_seconds():.3f}"

		logger.debug(f"解答開始: {user_id}")
		if self.pl is None:
			await interaction.followup.send(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error("Session.player is None")),
				ephemeral=True,
			)
			return
		if self.guild is None:
			await interaction.followup.send(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error("Session.guild is None")),
				ephemeral=True,
			)
			return

		# 早押しの受理判定 (core)
		answer_state = answers.AnswerState()
		answer_state.current_track_uri = self.pl.current.uri if self.pl.current is not None else None
		answer_state.answering_player_id = self.answering_player.id if self.answering_player is not None else None
		answer_state.can_answer = self.can_answered
		answer_state.question_started_at = self.q_start_time
		result = answers.check_raise_hand(answer_state, self.roster, user_id)

		# 再生中ではない場合
		if result is answers.RaiseHandError.NOT_PLAYING:
			await interaction.followup.send(
				embed=EmbedsTemplates.warning(
					description=t("msg.q.answering.not_playing.description"),
				),
				ephemeral=True,
				delete_after=2,
			)
			return

		if result is answers.RaiseHandError.ALREADY_ANSWERING:
			# 解答中のプレイヤー名を取得
			mb = await self.guild.get_or_fetch(discord.Member, self.answering_player.id)
			pn = mb.mention if mb is not None else str(self.answering_player.id)
			# 既に解答中のプレイヤーがいる場合はエラーメッセージを送信する
			await interaction.followup.send(
				embed=EmbedsTemplates.warning(
					title=t("msg.q.answering.title"),
					description=t("msg.q.answering.already.description", pn, answer_time_sec),
					icon="⚠️",
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		if result is answers.RaiseHandError.CANNOT_ANSWER:
			# 解答ができない状態の場合はエラーメッセージを送信する
			await interaction.respond(
				embed=EmbedsTemplates.warning(
					description=t("view.q.answer_button.cannot_answered"),
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		if result is answers.RaiseHandError.NOT_JOINED:
			# クイズに参加していないユーザーがクリックした場合はエラーメッセージを返す
			await interaction.followup.send(
				embed=EmbedsTemplates.error(description=t("view.q.answer_button.not_joined")),
				ephemeral=True,
				delete_after=3,
			)
			return

		if result is answers.RaiseHandError.MISS:
			# お手つき中のプレイヤーをはじく (プレイヤー数一人の場合ははじかない)
			await interaction.followup.send(
				embed=EmbedsTemplates.error(description=t("view.q.answer_button.miss")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 解答中プレイヤーを設定
		pl = result
		self.answering_player = pl

		# 解答中のプレイヤー名を取得
		mb = await self.guild.get_or_fetch(discord.Member, self.answering_player.id)
		pn = mb.mention if mb is not None else str(self.answering_player.id)

		# 部品を無効化
		# if interaction.view is not None:
		# 	interaction.view.disable_all_items()

		# 一時停止する
		self.ANSWERED.clear()
		logger.debug("- 一時停止")
		self.answer_pause_position = self.pl.position
		await self.pl.pause()

		# 全プレイヤーの不正解フラグをリセット
		self.refresh()

		# 解答中メッセージを表示する (解答ボタン付きメッセージの埋め込みを更新)
		await self._edit_q_msg(
			EmbedsTemplates.info(
				title=t("msg.q.answering.title"),
				description=t(
					"msg.q.answering.description",
					pn,
					answer_time_sec,
				),
				icon="💭",
			)
		)

		# 解答の選択肢セレクターを送信する
		_ = await interaction.followup.send(
			embed=EmbedsTemplates.info(title=t("msg.q.answer.title"), description=t("msg.q.answer.description"), icon="🗨️"),
			view=QuizAnswerSelectView(self.guild_id, await self.get_answer_tracks()),
			delete_after=5,  # 5秒後に自動削除
			ephemeral=True,
			wait=True,
		)

		# SFX
		await self.play_sfx(SFX.A)

		try:
			# ユーザーが解答するまで最大5秒待機
			await asyncio.wait_for(self.ANSWERED.wait(), timeout=5.0)
		except TimeoutError:
			# タイムアウトした場合 (解答がなかった場合)
			logger.debug("- 解答なし: 不正解判定")
			if self.answering_player:
				# 不正解
				self.answering_player.incorrect()
		finally:
			await asyncio.sleep(2)
			# 正解が出ておらず、次の問題に進んでいない場合のみ再生を再開する
			if self.can_answered:
				# 解答ができる状態にする
				self.answering_player = None
			# 再生再開
			logger.debug("- 再生再開")
			# 回答開始時の再生位置から3秒戻して再生する (回答開始時の再生位置が4秒未満の場合は最初から再生する)
			if self.answer_pause_position >= self.RESUME_SEEK_MIN_POSITION_MS:
				resume_position = self.answer_pause_position - self.RESUME_SEEK_BACK_MS
			else:
				resume_position = 0
			await self.pl.seek(resume_position)
			await self.pl.resume()

		# 解答中メッセージを問題表示に戻す
		await self._edit_q_msg(self._question_embed())

		# 部品を有効化
		# if interaction.view is not None:
		# 	interaction.view.enable_all_items()

	async def answer(self, user_id: int, answer: str) -> mafic.Track | None:
		"""解答する"""
		logger.debug(f"解答判定: {user_id} - {answer}")
		if self.pl is None:
			await DebugLogger.report_internal_error("Session.player is None")
			return None
		if self.pl.current is None:
			await DebugLogger.report_internal_error("Session.player.current is None")
			return None
		if not self.roster.is_joined(user_id):
			await DebugLogger.report_internal_error("User is not in players")
			return None

		# 回答者を取得
		player = await self.get_player(user_id)
		if player is None:
			await DebugLogger.report_internal_error("Player not found")
			# 解答者をリセット
			self.answering_player = None
			self.ANSWERED.set()
			return None

		if answers.is_correct(answer, self.pl.current.uri):
			logger.debug("- 正解")
			# 解答ができない状態にする
			self.can_answered = False
			correct_track = self.pl.current
			# 正解
			player.correct()
			# 次の問題へ進む
			# logger.debug("- 次の問題へ")
			# self.NEXT.set()
			# await self.pl.stop()
			self.ANSWERED.set()
			return correct_track
		# 不正解
		logger.debug("- 不正解")
		# 解答ができる状態にする
		self.can_answered = True
		player.incorrect()
		self.ANSWERED.set()
		return None
