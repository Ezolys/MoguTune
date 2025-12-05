import asyncio
import datetime
import logging
import random
import traceback
from dataclasses import dataclass, field
from os import getenv

import discord
import mafic
from pycord.localizer import t

from introqbot.chorus import YTMostReplayedAPI
from introqbot.client import client
from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.sfx import SFX

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class QuizReplayButtonView(discord.ui.View):
	def __init__(self, query: str, q_count: int, *args, **kwargs) -> None:
		super().__init__(timeout=None, *args, **kwargs)

		self.query = query
		self.q_count = q_count

		self.replay_button = discord.ui.Button(style=discord.ButtonStyle.primary, label=t("view.q.replay_button.label"), emoji="🔁")
		self.replay_button.callback = self.replay_button_callback
		self.add_item(self.replay_button)

	async def replay_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug("リプレイボタンクリック")

		# ユーザー&ギルドのチェック
		if interaction.user is None:
			await interaction.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=await DebugLogger.report_internal_error(f"{__class__.__name__} interaction.user is None")
				)
			)
			return
		if not isinstance(interaction.user, discord.Member):
			await interaction.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=await DebugLogger.report_internal_error(f"{__class__.__name__} interaction.user is not a Member")
				)
			)
			return
		if interaction.guild is None:
			await interaction.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=await DebugLogger.report_internal_error(f"{__class__.__name__} interaction.guild is None")
				)
			)
			return

		# クイズを開始する
		await prepare_play(interaction, interaction.user, interaction.guild, self.query, q_count=self.q_count)


class QuizNextQButtonView(discord.ui.View):
	def __init__(self, session_id: int, disabled: bool = False, *args, **kwargs) -> None:
		super().__init__(timeout=None, *args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			asyncio.run(DebugLogger.report_internal_error("QuizAnswerSelectView.session is None"))
			return

		# 次の問題があるかどうかに応じてラベルと絵文字を設定
		label, emoji = (
			(t("view.q.next_q_button.label.next"), "⏭️")
			if not self.session.current_q_number >= self.session.q_tracks_count
			else (t("view.q.next_q_button.label.end"), "🏁")
		)

		self.next_q_button = discord.ui.Button(style=discord.ButtonStyle.primary, label=label, emoji=emoji, disabled=disabled)
		self.next_q_button.callback = self.next_q_button_callback
		self.add_item(self.next_q_button)

	# 解答ボタン
	async def next_q_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"次の問題ボタンクリック: {self.session_id}")

		if interaction.user is None:
			await interaction.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=(await DebugLogger.report_internal_error(f"{self.__class__.__name__}.interaction.user is None"))
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# セッションを取得し直す
		self.session = quiz_session_manager.get_session(self.session_id)

		# セッションが存在するかチェック
		if self.session is None:
			await interaction.response.send_message(
				embed=EmbedsTemplates.error(description=t("view.q.next_q_button.session_not_found")),
				ephemeral=True,
				delete_after=3,
			)
			return

		if interaction.message is None:
			await interaction.response.send_message(
				embed=EmbedsTemplates.internal_error(
					error_code=await DebugLogger.report_internal_error("QuizNextQButtonView.interaction.message is None")
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# クイズのオーナーだけがこのボタンを押せるようにする
		if self.session.owner is not None and self.session.owner.id != interaction.user.id:
			await interaction.response.send_message(
				embed=EmbedsTemplates.error(
					description=t("view.q.next_q_button.do_not_have_permission"),
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 正解メッセージを削除する
		try:
			await interaction.message.delete()
		except discord.errors.NotFound:
			pass
		# 再生停止 (=次の問題へ)
		await self.session.pl.stop()
		self.session.NEXT.set()


class QuizAnswerSelectView(discord.ui.View):
	def __init__(self, session_id: int, answer_tracks: list[mafic.Track], *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)

		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			asyncio.run(DebugLogger.report_internal_error("QuizAnswerSelectView.session is None"))
			return

		logger.debug("Answer Select Options")
		for at in answer_tracks:
			logger.debug(f"{at.title}: {at.uri}")

		self.answer_select = discord.ui.Select(discord.ComponentType.string_select)
		# 解答候補一覧
		for tr in answer_tracks:
			# タイトルを生成
			# YouTube の場合はアーティスト名を含めない
			_title = tr.title if tr.source == "youtube" else tr.title + " - " + tr.author
			if len(_title) > 90:
				_title = _title[:90] + "..."  # 100文字以内に収まるようにする
			self.answer_select.options.append(
				discord.SelectOption(
					label=_title,
					value=tr.uri,
				)
			)
		self.answer_select.callback = self.answer_select_callback
		self.add_item(self.answer_select)

	# 解答選択肢
	async def answer_select_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"解答選択肢クリック: {self.session_id}")

		if interaction.user is None:
			await interaction.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=(await DebugLogger.report_internal_error(f"{self.__class__.__name__}.interaction.user is None"))
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# セッションを取得し直す
		self.session = quiz_session_manager.get_session(self.session_id)

		# セッションが存在するかチェック
		if self.session is None:
			_ = await interaction.response.send_message(
				embed=EmbedsTemplates.error(description=t("view.q.answer_select.session_not_found")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# クリックしたユーザーが解答者ではない場合はエラーメッセージを返す
		if self.session.answering_player is not None and self.session.answering_player.id != interaction.user.id:
			_ = await interaction.response.send_message(
				embed=EmbedsTemplates.error(description=t("view.q.answer_select.do_not_have_permission.description")),
				ephemeral=True,
				delete_after=3,
			)
			# 削除対象メッセージに追加
			self.session.next_cleanup_messages.append(await _.original_message())
			return

		result = await self.session.answer(interaction.user.id, interaction.data["values"][0])

		# 不正解
		# FIXME: 解答判定時に問題があった場合も None が返ってきて不正解判定になるので、問題があった場合は別の処理を行うようにする
		if result is None:
			# タイトルを生成
			# YouTube の場合はアーティスト名を含めない
			_track = self.session.get_track_from_uri(interaction.data["values"][0])
			_title = "Unknown" if _track is None else _track.title if _track.source == "youtube" else _track.title + " - " + _track.author
			# メッセージを送信
			_ = await interaction.response.send_message(
				embed=EmbedsTemplates.error(
					title=t("view.q.answer_select.incorrect.title"),
					description=t("view.q.answer_select.incorrect.description", _title),
					icon="❌",
				),
				ephemeral=True,
				delete_after=2,
			)
			# SFX
			await self.session.play_sfx(SFX.INCORRECT)
			await asyncio.sleep(1)
		# 正解
		else:
			# タイトルを生成
			# YouTube の場合はアーティスト名を含めない
			_track = result
			_title = "Unknown" if _track is None else _track.title if _track.source == "youtube" else _track.title + " - " + _track.author
			# 埋め込みメッセージを生成
			_embed = EmbedsTemplates.success(
				title=t("view.q.answer_select.correct.title"),
				description=t("view.q.answer_select.correct.description", interaction.user.mention, _title, _track.uri),
				icon="✅",
			).set_image(url=_track.artwork_url)  # ジャケットを設定
			# メッセージを送信
			next_q_button = QuizNextQButtonView(self.session_id, disabled=True)
			_ = await interaction.response.send_message(
				embed=_embed,
				view=next_q_button,  # 次の問題へ ボタン
				# ephemeral=True,
				# delete_after=3,
			)
			# 削除対象メッセージに追加
			self.session.next_cleanup_messages.append(await _.original_message())
			# SFX
			await self.session.play_sfx(SFX.CORRECT, restore=False)  # restore を False にして解答できないままにする
			await asyncio.sleep(1)

			# 答えの楽曲を再生する (終了時間を None にして最後まで再生する)
			# ソースが YouTube の場合は YTMostReplayedAPI からリプレイ回数が最も多い部分を取得してそこから再生する
			# if self.session.pl.current is not None and self.session.pl.current.uri is not None:
			logger.debug("- 正解後再生開始")
			_position = 0
			_uri = await self.session.resolve_youtube_track_uri(_track)
			if _uri is None:
				_uri = _track.uri

			if _uri is not None and ("youtube.com" in _uri or "youtu.be" in _uri):
				_position = await YTMostReplayedAPI.get_chorus_info(_uri)
				logger.info(f"Play Position: {_position}")
				if _position is None:
					_position = 0
			logger.debug(f"Resuming track: {_track.uri} at {_position}")
			await self.session.pl.play(_track, start_time=_position, volume=self.session.PL_VOLUME)

			# 次の問題へボタンを有効化
			next_q_button.enable_all_items()
			await _.edit_original_response(view=next_q_button)


class QuizAnswerButtonView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(timeout=None, *args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			asyncio.run(DebugLogger.report_internal_error("QuizAnswerSelectView.session is None"))
			return

		# 解答ボタン
		self.answer_button = discord.ui.Button(style=discord.ButtonStyle.green, label=t("view.q.answer_button.label"), emoji="💭")
		self.answer_button.callback = self.answer_button_callback
		self.add_item(self.answer_button)

		# 問題スキップボタン
		self.skip_button = discord.ui.Button(style=discord.ButtonStyle.gray, label=t("view.q.skip_button.label"), emoji="⏭️")
		self.skip_button.callback = self.skip_button_callback
		self.add_item(self.skip_button)

	# 解答ボタン
	async def answer_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"解答ボタンクリック: {self.session_id}")

		if interaction.user is None:
			await interaction.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=(await DebugLogger.report_internal_error(f"{self.__class__.__name__}.interaction.user is None"))
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		await interaction.response.defer()

		# セッションを取得し直す
		self.session = quiz_session_manager.get_session(self.session_id)

		# セッションが存在するかチェック
		if self.session is None:
			# セッションが見つからない場合はエラーメッセージを送信する
			await interaction.respond(
				embed=EmbedsTemplates.error(description=t("view.q.skip_button.session_not_found")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 再生停止&解答セレクター送信
		await self.session.raise_hand(interaction, interaction.user.id)

	# スキップボタン
	async def skip_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"スキップボタンクリック: {self.session_id}")

		if interaction.user is None:
			await interaction.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=(await DebugLogger.report_internal_error(f"{self.__class__.__name__}.interaction.user is None"))
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# セッションを取得し直す
		self.session = quiz_session_manager.get_session(self.session_id)

		# セッションが存在するかチェック
		if self.session is None:
			# セッションが見つからない場合はエラーメッセージを送信する
			await interaction.respond(
				embed=EmbedsTemplates.error(description=t("view.q.skip_button.session_not_found")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# クイズのオーナーだけがこのボタンを押せるようにする
		if self.session.owner is not None and self.session.owner.id != interaction.user.id:
			await interaction.respond(
				embed=EmbedsTemplates.error(
					description=t("view.q.skip_button.do_not_have_permission"),
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 楽曲を再生していない場合はエラーメッセージを返す
		if self.session.pl.current is None:
			await interaction.respond(
				embed=EmbedsTemplates.error(description=t("view.q.skip_button.not_playing")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 解答ができない状態の場合はエラーメッセージを送信する
		if not self.session.can_answered or self.session.answering_player is not None:
			await interaction.respond(
				embed=EmbedsTemplates.warning(
					description=t("view.q.skip_button.cannot_skipped"),
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# クリックしたプレイヤーを取得
		pl = await self.session.get_player(interaction.user.id)

		# クイズに参加していないユーザーがクリックした場合はエラーメッセージを返す
		if pl is None:
			await interaction.followup.send(
				embed=EmbedsTemplates.error(description=t("view.q.skip_button.not_joined")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 解答ができない状態にする
		self.session.can_answered = False

		# 通知メッセージを表示させるために問題終了後の待機時間を4秒にする
		self.session.q_wait_seconds = 4

		# 通知メッセージに情報を表示するために再生している楽曲を保持する
		pl_current = self.session.pl.current

		# トラックを取得
		_track = pl_current
		# タイトルを生成
		# YouTube の場合はアーティスト名を含めない
		_title = "Unknown" if _track is None else _track.title if _track.source == "youtube" else _track.title + " - " + _track.author
		# 埋め込みメッセージを生成
		_embed = EmbedsTemplates.info(
			title=t("msg.q.skip.title"),
			description=t("msg.q.skip.description", _title, _track.uri),
			icon="⏭️",
		).set_image(url=_track.artwork_url)  # ジャケットを設定

		# 通知メッセージを送信する
		next_q_button = QuizNextQButtonView(self.session_id, disabled=True)  # 次の問題へ ボタン
		msg = await interaction.respond(
			embed=_embed,
			view=next_q_button,
		)

		# 削除対象メッセージに追加
		if isinstance(msg, discord.Interaction):
			msg = await msg.original_message()
		self.session.next_cleanup_messages.append(msg)

		# 答えの楽曲を再生する
		# ソースが YouTube の場合は YTMostReplayedAPI からリプレイ回数が最も多い部分を取得してそこから再生する
		if self.session.pl.current is not None and self.session.pl.current.uri is not None:
			logger.debug("- スキップ後再生開始")
			_position = 0
			_uri = await self.session.resolve_youtube_track_uri(self.session.pl.current)
			if _uri is None:
				_uri = self.session.pl.current.uri

			if _uri is not None and ("youtube.com" in _uri or "youtu.be" in _uri):
				_position = await YTMostReplayedAPI.get_chorus_info(_uri)
				logger.info(f"Play Position: {_position}")
				if _position is None:
					_position = 0
			logger.debug(f"Resuming track (Skip): {pl_current.uri} at {_position}")
			await self.session.pl.play(pl_current, start_time=_position, volume=self.session.PL_VOLUME)

		# 次の問題へボタンを有効化
		next_q_button.enable_all_items()
		await msg.edit(view=next_q_button)


@dataclass
class QuizPlayer:
	"""クイズのプレイヤー (参加者)"""

	id: int
	"""プレイヤーのID"""
	point: int = 0
	"""ポイント (正答数)"""
	miss: bool = False
	"""不正解フラグ"""

	def correct(self) -> None:
		"""ポイントを1増やす"""
		self.point += 1

	def incorrect(self) -> None:
		"""不正解フラグを立てる"""
		self.miss = True

	def incorrect_reset(self) -> None:
		"""不正解フラグを消す"""
		self.miss = False

	def reset(self) -> None:
		"""ポイントと不正解フラグをリセット"""
		self.point = 0
		self.miss = False


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

	players: list[QuizPlayer] = field(default_factory=list)
	"""参加するプレイヤーの一覧"""
	queue: list[int] = field(default_factory=list)
	"""参加待ちのプレイヤーのID"""
	playing: bool = False
	"""クイズが開始されているかどうか"""

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

	next_cleanup_messages: list[discord.Message | discord.WebhookMessage] = field(default_factory=list)
	"""次の問題開始時に削除するメッセージのリスト"""

	can_answered: bool = False
	"""解答ができる状態かどうか"""

	NEXT: asyncio.Event = field(default_factory=asyncio.Event)
	ANSWERED: asyncio.Event = field(default_factory=asyncio.Event)
	SFX_FINISHED: asyncio.Event = field(default_factory=asyncio.Event)
	"""SFX再生完了イベント"""

	is_playing_sfx: bool = False
	"""SFXを再生しているかどうか"""
	original_track_before_sfx: mafic.Track | None = None
	"""SFX再生前のトラック"""
	original_position_before_sfx: int = 0
	"""SFX再生前の再生位置"""
	was_playing_before_sfx: bool = False
	"""SFX再生前に再生中だったかどうか"""

	async def add_player(self, user_id: int) -> None:
		"""プレイヤーを追加"""
		if self.is_player_joined(user_id):
			return
		logger.debug(f"プレイヤー追加: {user_id}")
		self.players.append(QuizPlayer(user_id))

	async def remove_player(self, user_id: int) -> None:
		"""プレイヤーを削除"""
		if not self.is_player_joined(user_id):
			return
		logger.debug(f"プレイヤー削除: {user_id}")
		self.players = [player for player in self.players if player.id != user_id]
		# プレイヤーが0人になったらクイズを終了する
		if len(self.players) == 0:
			logger.debug("- プレイヤー数0人: クイズ終了")
			await self.end()
		# オーナーが退出したらクイズを終了する
		elif self.owner is not None and self.owner.id == user_id:
			logger.debug("- オーナー退出: クイズ終了")
			await self.end()

	async def add_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを追加"""
		if user_id in self.queue:
			return
		logger.debug(f"参加待ちプレイヤー追加: {user_id}")
		self.queue.append(user_id)

	async def remove_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを削除"""
		if user_id not in self.queue:
			return
		logger.debug(f"参加待ちプレイヤー削除: {user_id}")
		self.queue.remove(user_id)

	async def join_queued_players(self) -> None:
		"""参加待ちのプレイヤー全員を参加させる"""
		logger.debug("参加待ちプレイヤー参加")
		for user_id in self.queue:
			logger.debug(f"- {user_id}")
			await self.add_player(user_id)
		self.queue = []

	def is_player_joined(self, user_id: int) -> bool:
		"""プレイヤーが参加しているかどうかを返す"""
		return user_id in [player.id for player in self.players]

	async def join_player(self, user_id: int) -> None:
		"""プレイヤーを参加させる

		既にクイズが開始されている場合は順番待ちに追加する
		"""
		if not self.is_player_joined(user_id):
			if self.playing:
				await self.add_queue(user_id)
			else:
				await self.add_player(user_id)

	async def get_player(self, user_id: int) -> QuizPlayer | None:
		"""プレイヤーを取得"""
		for player in self.players:
			if player.id == user_id:
				return player
		return None

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

		q_track = self.pl.current
		# 正解の曲を除いたリストを作成
		other_tracks = [t for t in self.q_original_tracks if t.uri != q_track.uri]
		# ダミーの選択肢を4つランダムにサンプリング
		dummy_tracks = random.sample(other_tracks, 4)
		# 正解の曲を加えてシャッフル
		answer_options = dummy_tracks + [q_track]
		random.shuffle(answer_options)
		return answer_options

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

	def refresh(self) -> None:
		"""全プレイヤーの不正解フラグをリセット"""
		[player.incorrect_reset() for player in self.players]

	def reset(self) -> None:
		"""クイズセッションをリセット"""
		# 全プレイヤーのポイントと不正解フラグをリセット
		[player.reset() for player in self.players]
		# 各変数をリセット
		self.q_original_tracks = []
		self.q_tracks = []
		self.q_tracks_count = 0
		self.current_q_number = 0
		self.q_start_time = None
		self.answering_player = None
		self.owner = None

	async def play_sfx(self, sfx_query: str | SFX, restore: bool = True) -> None:
		"""SFXを再生する

		再生中の楽曲を一時停止し、SFXを再生したあと、元の楽曲の再生を再開する
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

		logger.debug(f"Searching YouTube for: {track.author} - {track.title} (ISRC: {_isrc})")
		try:
			if _isrc:
				_search_query = f'ytsearch:"{_isrc}"'
			else:
				_search_query = f"ytsearch:{track.author} - {track.title}"

			_search_results = await self.pl.fetch_tracks(_search_query, search_type=mafic.SearchType.YOUTUBE_MUSIC)
			if _search_results and isinstance(_search_results, list) and len(_search_results) > 0:
				_uri = _search_results[0].uri
				logger.debug(f"Found YouTube track (ISRC): {_uri}")
				return _uri
			# ISRC で見つからなかった場合はタイトルで再検索
			if _isrc:
				logger.warning("YouTube track not found via ISRC. Retrying with title...")
				_search_query = f"ytsearch:{track.author} - {track.title}"
				_search_results = await self.pl.fetch_tracks(_search_query, search_type=mafic.SearchType.YOUTUBE_MUSIC)
				if _search_results and isinstance(_search_results, list) and len(_search_results) > 0:
					_uri = _search_results[0].uri
					logger.debug(f"Found YouTube track (Title): {_uri}")
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

	async def play(self, tracks: mafic.Playlist, q_count: int, owner_id: int) -> bool | str:
		"""クイズを開始する"""
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

			# トラック一覧
			self.q_original_tracks = tracks.tracks
			# 重複したトラックを除く
			unique_tracks = []
			seen_uris = set()
			for track in self.q_original_tracks:
				if track.uri is None:  # URI が None の楽曲は除く
					continue
				if track.uri not in seen_uris:
					unique_tracks.append(track)
					seen_uris.add(track.uri)
			self.q_original_tracks = unique_tracks

			# トラック一覧から指定された数だけランダムに取り出す (問題の生成)
			self.q_tracks = random.sample(tracks.tracks, len(tracks.tracks))[:q_count]
			self.q_tracks_count = q_count

			# 楽曲数が2曲未満の場合はエラーメッセージを返す
			if len(self.q_original_tracks) < 2:
				await self.voice_channel.send(embed=EmbedsTemplates.error(description=t("msg.q.init.must_be_at_least_two_songs")))
				# 終了
				self.playing = False
				self.reset()
				return False

			# 有効なトラック数が問題数+1よりも少ない場合はエラーメッセージを返す
			if len(self.q_original_tracks) < q_count:
				await self.voice_channel.send(
					embed=EmbedsTemplates.error(description=t("msg.q.init.not_enough_song", len(self.q_original_tracks), q_count))
				)
				# 終了
				self.playing = False
				self.reset()
				return False

			logger.debug(f"クイズ開始: {self.guild_id}/{self.channel_id}")

			logger.debug("- プレイヤー一覧生成")
			# プレイヤー一覧テキストを生成
			player_mentions = []
			for p in self.players:
				member: discord.Member | None = await self.guild.get_or_fetch(discord.Member, p.id)
				if member is not None:
					if member.mention:
						player_mentions.append(member.mention)
					else:
						player_mentions.append(member.display_name)
			player_list_text = "  - " + "\n  - ".join(player_mentions)

			# クイズ開始メッセージを送信
			start_msg = await self.voice_channel.send(
				embed=EmbedsTemplates.info(
					title=t("msg.q.init.title"),
					description=t("msg.q.init.description", tracks.name, q_count, player_list_text),
					icon="▶️",
				)
			)
			# 問題開始メッセージを送信
			q_msg = await self.voice_channel.send(
				embed=EmbedsTemplates.info(title=t("msg.q.start.title", "-"), description=t("msg.q.start.description"), icon="❔"),
				view=QuizAnswerButtonView(self.guild_id),  # 回答ボタン
			)

			for i, q in enumerate(self.q_tracks, 1):
				if not self.playing:
					break

				logger.debug(f"{i}問目")

				self.current_q_number = i

				# 参加待ちのプレイヤーを参加させる
				await self.join_queued_players()

				# プレイヤー一覧テキストを更新する
				logger.debug("- プレイヤー一覧更新")
				player_mentions = []
				for p in self.players:
					member = await self.guild.get_or_fetch(discord.Member, p.id)
					if member is not None:
						if member.mention:
							player_mentions.append(member.mention)
						else:
							player_mentions.append(member.display_name)
				player_list_text = "  - " + "\n  - ".join(player_mentions)
				start_msg.embeds[0].description = t("msg.q.init.description", tracks.name, q_count, player_list_text)
				await start_msg.edit(embed=start_msg.embeds[0])

				self.NEXT.clear()

				logger.debug("- タイトル更新")
				# タイトルを更新
				q_msg.embeds[0].title = "❔ " + t("msg.q.start.title", str(i))
				await q_msg.edit(embed=q_msg.embeds[0])

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
				await self.pl.pause()  # 念の為一時停止

				# 解答ができない状態にする
				self.can_answered = False
				# 解答者をリセット
				self.answering_player = None
				# 全プレイヤーの不正解フラグをリセット
				self.refresh()

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
				# TODO: ただの一覧ではなく順位をつけて表示するようにする
				if len(self.players) == 0:  # プレイヤーが0人の場合は専用のメッセージを設定
					ranking_list = [t("msg.q.end.no_players")]
				else:
					ranking_list = []
					# ポイント順にソート
					sorted_players = sorted(self.players, key=lambda x: x.point, reverse=True)

					display_rank = 1
					for i, p in enumerate(sorted_players):
						# 前の人より点数が低ければ順位を更新 (同点の場合は順位を維持)
						if i > 0 and p.point < sorted_players[i - 1].point:
							display_rank = i + 1

						member = await self.guild.get_or_fetch(discord.Member, p.id)
						pn = "Unknown"
						if member is not None:
							pn = member.mention or member.display_name

						rank_icon = f"**{display_rank}**"
						if display_rank == 1:
							rank_icon = "🥇"
						elif display_rank == 2:
							rank_icon = "🥈"
						elif display_rank == 3:
							rank_icon = "🥉"

						pt = t("cmd.play.ranking.point") if p.point == 1 else t("cmd.play.ranking.points")
						ranking_list.append(f"{rank_icon} {pn}: **`{p.point}`** {pt}")
				# 結合
				ranking = "\n".join(ranking_list)

				# 終了メッセージを送信する
				await self.voice_channel.send(
					embed=EmbedsTemplates.info(title=t("msg.q.end.title"), description=t("msg.q.end.description", ranking), icon="🏁"),
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

		# 再生中ではない場合
		if self.pl.current is None:
			await interaction.followup.send(
				embed=EmbedsTemplates.warning(
					description=t("msg.q.answering.not_playing.description"),
				),
				ephemeral=True,
				delete_after=2,
			)
			return

		if self.answering_player is not None:
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

		if not self.can_answered:
			# 解答ができない状態の場合はエラーメッセージを送信する
			await interaction.respond(
				embed=EmbedsTemplates.warning(
					description=t("view.q.answer_button.cannot_answered"),
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# クリックしたプレイヤーを取得
		pl = await self.get_player(user_id)

		# クイズに参加していないユーザーがクリックした場合はエラーメッセージを返す
		if pl is None:
			await interaction.followup.send(
				embed=EmbedsTemplates.error(description=t("view.q.answer_button.not_joined")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# お手つき中のプレイヤーをはじく (プレイヤー数一人の場合ははじかない)
		if pl.miss and len(self.players) > 1:
			await interaction.followup.send(
				embed=EmbedsTemplates.error(description=t("view.q.answer_button.miss")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 解答中プレイヤーを設定
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
		await self.pl.pause()

		# 全プレイヤーの不正解フラグをリセット
		self.refresh()

		# 全プレイヤーに解答中メッセージを送信する
		as_msg = None
		if self.voice_channel is not None:
			as_msg = await self.voice_channel.send(
				embed=EmbedsTemplates.info(
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
				await self.pl.resume()

		# 解答中メッセージを削除
		try:
			if as_msg:
				await as_msg.delete()
		except discord.errors.NotFound:
			pass

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
		if user_id not in [player.id for player in self.players]:
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

		if self.pl.current.uri == answer:
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


@dataclass
class QuizSessionManager:
	"""クイズのセッションマネージャー"""

	sessions: dict[int, QuizSession] = field(default_factory=dict)

	def create_session(self, guild_id: int, channel_id: int, player: mafic.Player, query: str) -> QuizSession:
		"""セッションを新規作成する"""
		logger.debug(f"セッション新規作成: {guild_id}/{channel_id}")
		self.sessions[guild_id] = QuizSession(guild_id, channel_id, player, query)
		return self.sessions[guild_id]

	def delete_session(self, guild_id: int) -> None:
		"""セッションを削除する"""
		logger.debug(f"セッション削除: {guild_id}")
		if guild_id in self.sessions:
			del self.sessions[guild_id]

	def get_session(self, guild_id: int) -> QuizSession | None:
		"""セッションを取得する

		存在しない場合は None を返す
		"""
		return self.sessions.get(guild_id)

	async def end_session(self, guild_id: int) -> None:
		"""セッションを終了して削除する"""
		logger.debug(f"セッション終了: {guild_id}")
		if guild_id in self.sessions:
			session = self.sessions[guild_id]
			await self.sessions[guild_id].end()
			self.delete_session(guild_id)
			# ボイスチャンネルから切断する
			try:
				if session.voice_channel is not None and session.voice_channel.guild.voice_client is not None:
					await session.voice_channel.guild.voice_client.disconnect()
			except Exception:
				logger.error("- ボイスチャンネル切断エラー")
				logger.error(traceback.format_exc())
				await DebugLogger.report_internal_error(traceback.format_exc())


quiz_session_manager = QuizSessionManager()


async def prepare_play(
	inter: discord.Interaction,
	user: discord.Member,
	guild: discord.Guild,
	query: str = "",
	q_count: int = 10,
) -> None:
	"""クイズを開始する"""
	session = None
	try:
		# プレイリストのURLとプリセットどちらも指定されていない場合はエラーメッセージを返す
		if query == "":
			await inter.respond(embed=EmbedsTemplates.error(description=t("cmd.play.no_query")), ephemeral=True)
			return

		if isinstance(inter, discord.Message):
			msg = inter
		else:
			# 準備中メッセージを送信
			_inter = await inter.response.send_message(
				embed=EmbedsTemplates.info(title=t("cmd.play.preparing.title"), description=t("cmd.play.preparing.description"), icon="🔳"),
				ephemeral=True,
			)
			msg = await _inter.original_message()

		if msg is None:
			return

		# ユーザーがボイスチャンネルに接続しているかチェック
		if user.voice is None:
			# ボイスチャンネルに参加していない場合はエラー
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.start.not_specified_voice_channel")))
			return
		if not isinstance(user.voice.channel, discord.VoiceChannel):
			# 参加しているチャンネルがボイスチャンネルではない場合はエラー
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.start.not_specified_voice_channel")))
			return

		voice_channel: discord.VoiceChannel = user.voice.channel

		# サーバー内で既にクイズが開始されているかチェック
		session = quiz_session_manager.get_session(guild.id)
		if session:
			await msg.edit(
				embed=EmbedsTemplates.error(description=t("cmd.start.already_started", guild.get_channel(session.channel_id).mention))
			)
			return

		# セッション数制限チェック
		max_sessions = int(getenv("MAX_SESSIONS", "0"))
		if max_sessions > 0 and len(quiz_session_manager.sessions) >= max_sessions:
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.start.limit_reached")))
			return

		# VCへ接続
		if voice_channel.guild.voice_client is not None:
			# 既に接続している場合は一度切断する
			await voice_channel.guild.voice_client.disconnect()
			await asyncio.sleep(2)
		player = await voice_channel.connect(cls=mafic.Player)

		# 検索タイプ
		search_type = mafic.SearchType.YOUTUBE_MUSIC
		# search_type = mafic.SearchType[search_type]

		# プレイリストを検索
		logger.debug(f"プレイリスト検索 - {search_type}: {query}")
		try:
			tracks = await player.fetch_tracks(query, search_type)
		except Exception:
			if voice_channel.guild.voice_client:
				# 切断する
				await voice_channel.guild.voice_client.disconnect()
			await msg.edit(
				embed=EmbedsTemplates.internal_error(
					description=t("cmd.play.tracks_fetch_error"),
					error_code=await DebugLogger.report_internal_error(traceback.format_exc()),
				)
			)
			return

		# プレイリスト (楽曲) が見つからない場合
		if not tracks:
			if voice_channel.guild.voice_client:
				# 切断する
				await voice_channel.guild.voice_client.disconnect()
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.play.no_tracks_found")))
			return
		# 指定されたクエリーがプレイリストではない場合
		if isinstance(tracks, list):
			if voice_channel.guild.voice_client:
				# 切断する
				await voice_channel.guild.voice_client.disconnect()
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.play.not_a_playlist_url")))
			return

		# クイズセッションを新規作成
		session = quiz_session_manager.create_session(guild.id, voice_channel.id, player, query)
		bot_id = client.user.id if client.user else 0
		# VCに参加しているユーザーをプレイヤーとして追加する
		for u in voice_channel.voice_states:  # .members を使うと正しくメンバー一覧を取得できない
			# 自分自身は除外
			_m = await guild.get_or_fetch(discord.Member, u)
			if u == bot_id:
				continue
			# ボットは除外
			if _m is not None and _m.bot:
				continue
			# クイズにユーザーを追加
			await session.add_player(u)

		# クイズ準備完了メッセージ送信
		await msg.edit(
			embed=EmbedsTemplates.info(
				title=t("cmd.play.preparing_complete.title"),
				description=t("cmd.play.preparing_complete.description", voice_channel.mention),
				icon="☑️",
			)
		)
		# クイズ開始
		play_result = await session.play(tracks, q_count, user.id)

		# 内部エラー
		if isinstance(play_result, str):
			await msg.edit(embed=EmbedsTemplates.internal_error(error_code=play_result))

		# クイズセッションを終了する
		await quiz_session_manager.end_session(session.guild_id)

		# ボイスチャンネルから切断できていない場合は念の為切断する
		if voice_channel is not None and voice_channel.guild.voice_client is not None:
			await voice_channel.guild.voice_client.disconnect()

	except Exception:
		try:
			# クイズセッションを終了する
			if session is not None:
				await quiz_session_manager.end_session(session.guild_id)
		except Exception:
			logger.error("クイズ実行エラー - クイズ終了失敗")
			logger.error(traceback.format_exc())
		err_code = await DebugLogger.report_internal_error("クイズ実行エラー\n\n" + traceback.format_exc())
		try:
			if inter.channel is not None and not isinstance(
				inter.channel, (discord.CategoryChannel, discord.ForumChannel, discord.MediaChannel)
			):
				await inter.channel.send(embed=EmbedsTemplates.internal_error(error_code=err_code))
		except Exception:
			logger.exception("Internal Error Message Send Failed")


# ボイスチャンネルステータス変更時 (参加/退出等) イベント
@client.listen()
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
	session = quiz_session_manager.get_session(member.guild.id)
	# 対象のサーバーでクイズが行われている場合はメンバーのチェックを実行する
	if session is None:
		return

	# クイズが行われているボイスチャンネルに参加した
	if after.channel is not None and after.channel.id == session.channel_id:
		# 自分自身とボットは除外
		if member.id == client.user.id or member.bot:
			return
		# 参加待ちの列へ追加する
		await session.add_queue(member.id)

	# クイズが行われているボイスチャンネルから退出した
	elif before.channel is not None and after.channel is None and before.channel.id == session.channel_id:
		# 自分が退出した場合はクイズを終了する
		if member.id == client.user.id:
			await quiz_session_manager.end_session(member.guild.id)
			return
		# プレイヤーを削除する 場合によってはクイズ終了
		await session.remove_player(member.id)
		await session.remove_queue(member.id)


# 再生開始時イベント
@client.listen()
async def on_track_start(event: mafic.TrackEndEvent):
	assert isinstance(event.player, mafic.Player)
	guild_id = event.player.guild.id
	logger.debug(f"再生開始イベント: {guild_id}")


# 再生終了時イベント
@client.listen()
async def on_track_end(event: mafic.TrackEndEvent):
	assert isinstance(event.player, mafic.Player)
	guild_id = event.player.guild.id
	logger.debug(f"再生終了イベント: {guild_id} ({event.reason})")
	session = quiz_session_manager.get_session(guild_id)
	if session is None:
		return

		# SFXの再生が終了した場合
	if session.is_playing_sfx:
		logger.debug(f"SFX再生終了イベント: {guild_id}")
		# 元の楽曲の再生を再開
		if session.original_track_before_sfx:
			try:
				# REPLACED の場合は無視する
				if event.reason == mafic.EndReason.REPLACED:
					logger.debug("- REPLACEDのため無視")
					return

				# 元の楽曲を復帰
				await session.pl.play(
					session.original_track_before_sfx,
					start_time=session.original_position_before_sfx,
					volume=session.PL_VOLUME,
				)

				# SFX再生前に一時停止していた場合は一時停止状態に戻す
				if not session.was_playing_before_sfx:
					logger.debug("- SFX再生前は一時停止中だったため、一時停止状態に戻します")
					await session.pl.pause()
			except Exception:
				logger.error("SFX終了後の楽曲復帰に失敗しました")
				logger.error(traceback.format_exc())
		else:
			# 元の楽曲がない = SFX再生前は何も再生していない状態だった
			logger.debug("- SFX再生前は何も再生していなかったため、復帰しません")

		session.SFX_FINISHED.set()
		return

	# クイズの楽曲が終了した場合、次の問題へ進む
	if event.reason == mafic.EndReason.FINISHED:
		session.NEXT.set()
