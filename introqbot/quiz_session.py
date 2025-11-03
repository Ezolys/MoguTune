import asyncio
import logging
import random
from dataclasses import dataclass, field

import discord
import mafic
from pycord.localizer import t

from introqbot.debug_logger import DebugLogger
from introqbot.embeds import Notification

logger = logging.getLogger(__name__)


class QuizJoinView(discord.ui.View):
	session_id: int

	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)
		self.session_id = session_id

	@discord.ui.button(emoji="arrow_right")
	async def button_callback(self, button: discord.Button, interaction: discord.Interaction) -> None:
		logger.debug(f"参加ボタンクリック: {self.session_id}")
		session = quiz_session_manager.get_session(self.session_id)
		# セッションが存在するかチェック
		if session is None:
			await interaction.respond(embed=Notification.error(description=t("view.q.join.msg.session_not_found")), ephemeral=True)
			return

		# 既にクイズに参加しているかどうかチェック
		if session.is_player_joined(interaction.user.id):
			await interaction.respond(embed=Notification.warning(description=t("view.q.join.msg.already_joined")), ephemeral=True)
			return

		# クイズが行われているボイスチャンネルにユーザーが接続しているかチェック
		if interaction.user.voice is None:
			await interaction.respond(
				embed=Notification.warning(description=t("view.q.join.msg.voice_channel_not_connected")), ephemeral=True
			)
			return
		if interaction.user.voice.channel.id != session.channel_id:
			await interaction.respond(
				embed=Notification.warning(description=t("view.q.join.msg.voice_channel_not_connected")), ephemeral=True
			)
			return

		# セッションにボタンをクリックしたユーザーを追加する
		session.join_player(interaction.user.id)

		await interaction.respond(embed=Notification.success(description=t("view.q.join.msg.joined")), ephemeral=True)


class QuizAnswerSelectView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)

		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			asyncio.run(DebugLogger.report_internal_error("QuizAnswerSelectView.session is None"))
			return

		logger.debug("Answer Select Options")
		for at in self.session.get_answer_tracks():
			logger.debug(f"{at.title}: {at.uri}")

		answer_select = discord.ui.Select(discord.ComponentType.string_select)
		answer_select.options = [discord.SelectOption(label=t.title, value=t.uri) for t in (self.session.get_answer_tracks())]
		answer_select.callback = self.answer_select_callback
		self.add_item(answer_select)

	# 解答選択肢
	async def answer_select_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"解答選択肢クリック: {self.session_id}")
		# セッションが存在するかチェック
		if self.session is None:
			await interaction.respond(embed=Notification.error(description=t("view.q.join.msg.session_not_found")), ephemeral=True)
			return

		result = await self.session.answer(interaction.user.id, interaction.data["values"][0])

		if result is not None:
			if result:  # 正解
				await interaction.respond(
					embed=Notification.success(
						title=t("view.q.answer_select.correct.title"), description=t("view.q.answer_select.correct.description")
					)
				)
			else:  # 不正解
				await interaction.respond(
					embed=Notification.error(
						title=t("view.q.answer_select.incorrect.title"), description=t("view.q.answer_select.incorrect.description")
					)
				)


class QuizAnswerButtonView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			asyncio.run(DebugLogger.report_internal_error("QuizAnswerSelectView.session is None"))
			return

		answer_button = discord.ui.Button(label=t("view.q.answer_button.label"))
		answer_button.callback = self.answer_button_callback
		self.add_item(answer_button)

	# 解答ボタン
	async def answer_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"解答ボタンクリック: {self.session_id}")
		# セッションが存在するかチェック
		if self.session is None:
			await interaction.respond(embed=Notification.error(description=t("view.q.join.msg.session_not_found")), ephemeral=True)
			return

		# 再生停止&解答セレクター送信
		await self.session.answer_pause(interaction.user.id)
		await interaction.response.pong()


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
	players: list[QuizPlayer] = field(default_factory=list)
	"""参加するプレイヤーの一覧"""
	queue: list[int] = field(default_factory=list)
	"""参加待ちのプレイヤーのID"""
	playing: bool = False
	"""クイズが開始されているかどうか"""

	answering_player: QuizPlayer | None = None
	"""現在解答中のプレイヤー"""

	q_original_tracks: list[mafic.Track] | None = None
	"""問題の元のトラック一覧"""
	q_tracks: list[mafic.Track] | None = None
	"""問題のトラック一覧"""

	guild: discord.Guild | None = None
	"""サーバー"""
	channel: discord.VoiceChannel | None = None
	"""ボイスチャンネル"""

	pl: mafic.Player | None = None
	NEXT: asyncio.Event = field(default_factory=asyncio.Event)

	def add_player(self, user_id: int) -> None:
		"""プレイヤーを追加"""
		self.players.append(QuizPlayer(user_id))

	def remove_player(self, user_id: int) -> None:
		"""プレイヤーを削除"""
		self.players = [player for player in self.players if player.id != user_id]

	def add_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを追加"""
		self.queue.append(user_id)

	def remove_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを削除"""
		self.queue.remove(user_id)

	def join_queued_players(self) -> None:
		"""参加待ちのプレイヤー全員を参加させる"""
		for user_id in self.queue:
			self.add_player(user_id)
		self.queue = []

	def is_player_joined(self, user_id: int) -> bool:
		"""プレイヤーが参加しているかどうかを返す"""
		return user_id in [player.id for player in self.players]

	def join_player(self, user_id: int) -> None:
		"""プレイヤーを参加させる

		既にクイズが開始されている場合は順番待ちに追加する
		"""
		if not self.is_player_joined(user_id):
			if self.playing:
				self.add_queue(user_id)
			else:
				self.add_player(user_id)

	def refresh(self) -> None:
		"""全プレイヤーの不正解フラグをリセット"""
		[player.incorrect_reset() for player in self.players]

	def reset(self) -> None:
		"""全プレイヤーのポイントと不正解フラグをリセット"""
		[player.reset() for player in self.players]

	def get_answer_tracks(self) -> list[mafic.Track]:
		"""解答候補のトラック一覧を生成"""
		if self.q_original_tracks is None:
			return []
		if self.q_tracks is None:
			return []
		if self.pl is None:
			return []
		if self.pl.current is None:
			return []

		original_tracks = random.sample(self.q_original_tracks, 4)
		q_track = self.pl.current
		original_tracks.append(q_track)
		random.shuffle(original_tracks)
		return original_tracks.copy()

	async def end(self) -> None:
		"""クイズを終了"""
		logger.debug(f"クイズ終了: {self.guild_id}/{self.channel_id}")

		if self.pl:
			await self.pl.stop()  # 再生を停止
			await self.pl.disconnect()  # ボイスチャンネルから切断
			self.pl = None
		self.playing = False
		self.q_original_tracks = None
		self.q_tracks = None
		self.guild = None
		self.channel = None
		self.pl = None
		self.NEXT.clear()
		self.reset()

	async def play(self, player: mafic.Player, tracks: mafic.Playlist, q_count: int) -> None:
		"""クイズを実行"""
		logger.debug(f"クイズ開始: {self.guild_id}/{self.channel_id}")

		self.playing = True

		self.pl = player

		self.guild = player.guild
		if self.guild is None:
			await DebugLogger.report_internal_error("クイズ開始処理失敗: Guild not found")
			return
		self.voice_channel: discord.VoiceChannel = self.guild.get_channel(self.channel_id)

		# プレイリストの場合はトラック一覧だけ取得する
		# if isinstance(tracks, mafic.Playlist):
		# 	tracks = tracks.tracks

		self.q_original_tracks = tracks.tracks
		# トラック一覧から指定された数だけランダムに取り出す (問題の生成)
		self.q_tracks = random.sample(tracks.tracks, q_count)

		# クイズ開始メッセージを送信
		await self.voice_channel.send(
			embed=Notification.info(title=t("msg.q.init.title"), description=t("msg.q.init.description", tracks.name, q_count))
		)
		await asyncio.sleep(3)

		for i, q in enumerate(self.q_tracks):
			if not self.playing:
				return

			# 問題開始メッセージを送信
			await self.voice_channel.send(
				embed=Notification.info(title=t("msg.q.start.title", i + 1), description=t("msg.q.start.description")),
				view=QuizAnswerButtonView(self.guild_id),  # 回答ボタン
			)
			await asyncio.sleep(3)
			# 再生
			self.NEXT.clear()
			await player.play(q, end_time=15000)  # ミリ秒
			await self.NEXT.wait()
			await player.pause()
			# 全プレイヤーの不正解フラグをリセット
			self.refresh()
			# 待機
			# await asyncio.sleep(15)
			# 再生停止
			# await player.stop()

		self.pl = None

		# ランキングテキストを生成
		# TODO: ただの一覧ではなく順位をつけて表示するようにする
		ranking = "- " + "\n- ".join([self.guild.get_member(p.id).mention + ": `" + str(p.point) + "`" for p in self.players])
		# 終了メッセージを送信する
		await self.voice_channel.send(embed=Notification.info(title=t("msg.q.end.title"), description=t("msg.q.end.description", ranking)))

		# 順番待ちプレイヤーを追加する
		self.join_queued_players()

	async def answer_pause(self, user_id: int) -> None:
		"""再生を一時停止して解答の選択肢を送信する"""
		logger.debug(f"回答開始: {user_id}")
		if self.pl is None:
			await DebugLogger.report_internal_error("Session.player is None")
			return
		if self.pl.current is None:
			await DebugLogger.report_internal_error("Session.player.current is None")
			return
		if user_id not in [player.id for player in self.players]:
			await DebugLogger.report_internal_error("User is not in players")
			return

		if self.answering_player is not None:
			return

		await self.voice_channel.send(
			embed=Notification.info(
				title=t("msg.q.answering.title"), description=t("msg.q.answering.description", self.guild.get_member(user_id).name)
			)
		)
		# 解答の選択肢セレクターを送信する
		msg = await self.voice_channel.send(
			embed=Notification.info(title=t("msg.q.answer.title"), description=t("msg.q.answer.description")),
			view=QuizAnswerSelectView(self.guild_id),
		)
		await self.pl.pause()
		await asyncio.sleep(5)
		await msg.delete()  # 選択肢メッセージを削除する
		await asyncio.sleep(1)
		# 再生を再開
		self.NEXT.clear()
		await self.pl.pause(pause=False)

	async def answer(self, user_id: int, answer_id: str) -> bool | None:
		"""回答する"""
		logger.debug(f"回答判定: {user_id} - {answer_id}")
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
		player = next(player for player in self.players if player.id == user_id)

		if self.pl.current.uri == answer_id:
			# 正解
			player.correct()
			# 次の問題へ進む
			self.NEXT.set()
			return True
		# 不正解
		player.incorrect()
		await asyncio.sleep(1)
		# 再生を再開
		self.NEXT.clear()
		await self.pl.pause(pause=False)
		return False


@dataclass
class QuizSessionManager:
	"""クイズのセッションマネージャー"""

	sessions: dict[int, QuizSession] = field(default_factory=dict)

	def create_session(self, guild_id: int, channel_id: int) -> QuizSession:
		"""セッションを新規作成"""
		logger.debug(f"セッション新規作成: {guild_id}/{channel_id}")
		self.sessions[guild_id] = QuizSession(guild_id, channel_id)
		return self.sessions[guild_id]

	def delete_session(self, guild_id: int) -> None:
		"""セッションを削除"""
		logger.debug(f"セッション削除: {guild_id}")
		del self.sessions[guild_id]

	def get_session(self, guild_id: int) -> QuizSession | None:
		"""セッションを取得

		存在しない場合は None を返す
		"""
		return self.sessions.get(guild_id)


quiz_session_manager = QuizSessionManager()
