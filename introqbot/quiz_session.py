import asyncio
import logging
import random
from dataclasses import dataclass, field

import discord
import mafic
from pycord.localizer import t

from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
			await interaction.respond(embed=EmbedsTemplates.error(description=t("view.q.join.msg.session_not_found")), ephemeral=True)
			return

		# 既にクイズに参加しているかどうかチェック
		if session.is_player_joined(interaction.user.id):
			await interaction.respond(embed=EmbedsTemplates.warning(description=t("view.q.join.msg.already_joined")), ephemeral=True)
			return

		# クイズが行われているボイスチャンネルにユーザーが接続しているかチェック
		if interaction.user.voice is None:
			await interaction.respond(
				embed=EmbedsTemplates.warning(description=t("view.q.join.msg.voice_channel_not_connected")), ephemeral=True
			)
			return
		if interaction.user.voice.channel.id != session.channel_id:
			await interaction.respond(
				embed=EmbedsTemplates.warning(description=t("view.q.join.msg.voice_channel_not_connected")), ephemeral=True
			)
			return

		# セッションにボタンをクリックしたユーザーを追加する
		session.join_player(interaction.user.id)

		await interaction.respond(embed=EmbedsTemplates.success(description=t("view.q.join.msg.joined")), ephemeral=True)


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
			await interaction.respond(embed=EmbedsTemplates.error(description=t("view.q.join.msg.session_not_found")), ephemeral=True)
			return

		if self.session.answering_player is not None:
			if self.session.answering_player.id != interaction.user.id:
				await interaction.respond(
					embed=EmbedsTemplates.error(description=t("view.q.answer_select.do_not_have_permission.description")),
					ephemeral=True,
					delete_after=3,
				)
				return

		result = await self.session.answer(interaction.user.id, interaction.data["values"][0])

		if result is not None:
			if result:  # 正解
				await interaction.respond(
					embed=EmbedsTemplates.success(
						title=t("view.q.answer_select.correct.title"),
						description=t("view.q.answer_select.correct.description", interaction.data["values"][0]),
						icon="✅",
					),
					ephemeral=True,
					delete_after=2,
				)
			else:  # 不正解
				await interaction.respond(
					embed=EmbedsTemplates.error(
						title=t("view.q.answer_select.incorrect.title"),
						description=t("view.q.answer_select.incorrect.description", interaction.data["values"][0]),
						icon="❌",
					),
					ephemeral=True,
					delete_after=2,
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

		self.answer_button = discord.ui.Button(label=t("view.q.answer_button.label"), emoji="💭")
		self.answer_button.callback = self.answer_button_callback
		self.add_item(self.answer_button)

	# 解答ボタン
	async def answer_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"解答ボタンクリック: {self.session_id}")

		await interaction.response.defer()

		# セッションが存在するかチェック
		if self.session is None:
			# セッションが見つからない場合はエラーメッセージを送信する
			await interaction.respond(
				embed=EmbedsTemplates.error(description=t("view.q.join.msg.session_not_found")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 再生停止&解答セレクター送信
		await self.session.raise_hand(interaction, interaction.user.id)


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

	players: list[QuizPlayer] = field(default_factory=list)
	"""参加するプレイヤーの一覧"""
	queue: list[int] = field(default_factory=list)
	"""参加待ちのプレイヤーのID"""
	playing: bool = False
	"""クイズが開始されているかどうか"""

	answering_player: QuizPlayer | None = None
	"""現在解答中のプレイヤー"""
	current_q_number: int = 0
	"""問題番号"""
	q_original_tracks: list[mafic.Track] | None = None
	"""問題の元のトラック一覧"""
	q_tracks: list[mafic.Track] | None = None
	"""問題のトラック一覧"""

	NEXT: asyncio.Event = field(default_factory=asyncio.Event)
	ANSWERED: asyncio.Event = field(default_factory=asyncio.Event)

	def add_player(self, user_id: int) -> None:
		"""プレイヤーを追加"""
		if self.is_player_joined(user_id):
			return
		logger.debug(f"プレイヤー追加: {user_id}")
		self.players.append(QuizPlayer(user_id))

	def remove_player(self, user_id: int) -> None:
		"""プレイヤーを削除"""
		if not self.is_player_joined(user_id):
			return
		logger.debug(f"プレイヤー削除: {user_id}")
		self.players = [player for player in self.players if player.id != user_id]

	def add_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを追加"""
		if user_id in self.queue:
			return
		logger.debug(f"参加待ちプレイヤー追加: {user_id}")
		self.queue.append(user_id)

	def remove_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを削除"""
		if user_id not in self.queue:
			return
		logger.debug(f"参加待ちプレイヤー削除: {user_id}")
		self.queue.remove(user_id)

	def join_queued_players(self) -> None:
		"""参加待ちのプレイヤー全員を参加させる"""
		logger.debug("参加待ちプレイヤー参加")
		for user_id in self.queue:
			logger.debug(f"- {user_id}")
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

	def get_player(self, user_id: int) -> QuizPlayer | None:
		"""プレイヤーを取得"""
		for player in self.players:
			if player.id == user_id:
				return player
		return None

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

		q_track = self.pl.current
		# 正解の曲を除いたリストを作成
		other_tracks = [t for t in self.q_original_tracks if t.uri != q_track.uri]
		# ダミーの選択肢を4つランダムにサンプリング
		dummy_tracks = random.sample(other_tracks, 4)
		# 正解の曲を加えてシャッフル
		answer_options = dummy_tracks + [q_track]
		random.shuffle(answer_options)
		return answer_options

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
		self.current_q_number = 0
		self.answering_player = None

	async def play(self, tracks: mafic.Playlist, q_count: int) -> None:
		"""クイズを開始"""
		self.playing = True
		self.reset()

		self.guild = self.pl.guild
		self.voice_channel = self.guild.get_channel(self.channel_id)
		if self.voice_channel is None:
			await DebugLogger.report_internal_error("クイズ開始処理失敗: Voice Channel not found")
			return
		if not isinstance(self.voice_channel, discord.VoiceChannel):
			await DebugLogger.report_internal_error("クイズ開始処理失敗: Channel is not Voice Channel")
			return

		self.q_original_tracks = tracks.tracks
		# トラック一覧から指定された数だけランダムに取り出す (問題の生成)
		self.q_tracks = random.sample(tracks.tracks, len(tracks.tracks))[:q_count]

		logger.debug(f"クイズ開始: {self.guild_id}/{self.channel_id}")

		# プレイヤー一覧テキストを生成
		player_list_text = "  - " + "\n  - ".join([self.guild.get_member(p.id).mention for p in self.players])
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
		await asyncio.sleep(1)

		for i, q in enumerate(self.q_tracks, 1):
			if not self.playing:
				return

			logger.debug(f"{i}問目")

			self.q_number = i

			# 参加待ちのプレイヤーを参加させる
			self.join_queued_players()

			# プレイヤー一覧テキストを更新する
			player_list_text = "  - " + "\n  - ".join([self.guild.get_member(p.id).mention for p in self.players])
			start_msg.embeds[0].description = t("msg.q.init.description", tracks.name, q_count, player_list_text)
			await start_msg.edit(embed=start_msg.embeds[0])

			self.NEXT.clear()

			# タイトルを更新
			q_msg.embeds[0].title = "❔ " + t("msg.q.start.title", str(i))
			await q_msg.edit(embed=q_msg.embeds[0])

			await asyncio.sleep(1)

			logger.debug("再生開始")

			# 再生
			await self.pl.play(q, end_time=15000)  # ミリ秒
			await self.NEXT.wait()

			logger.debug("再生終了")

			# 全プレイヤーの不正解フラグをリセット
			self.refresh()
			# 待機
			logger.debug("待機")
			await asyncio.sleep(3)

		# 解答ボタンを削除
		await q_msg.edit(view=None)

		# ランキングテキストを生成
		# TODO: ただの一覧ではなく順位をつけて表示するようにする
		ranking = "- " + "\n- ".join([self.guild.get_member(p.id).mention + ": `" + str(p.point) + "`" for p in self.players])
		# 終了メッセージを送信する
		await self.voice_channel.send(
			embed=EmbedsTemplates.info(title=t("msg.q.end.title"), description=t("msg.q.end.description", ranking), icon="🏁")
		)

		# 終了
		self.playing = False
		self.reset()

	async def raise_hand(self, interaction: discord.Interaction, user_id: int) -> None:
		"""再生を一時停止して解答の選択肢を送信する"""
		logger.debug(f"解答開始: {user_id}")
		if self.pl is None:
			await interaction.followup.send(
				embed=EmbedsTemplates.internal_error(
					description="Session.player is None", error_code=await DebugLogger.report_internal_error("Session.player is None")
				),
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
			# await interaction.followup.send(
			# 	embed=EmbedsTemplates.internal_error(
			# 		description="Session.player.current is None",
			# 		error_code=await DebugLogger.report_internal_error("Session.player.current is None"),
			# 	),
			# 	ephemeral=True,
			# )
			return
		# if user_id not in [player.id for player in self.players]:
		# 	await interaction.followup.send(
		# 		embed=EmbedsTemplates.internal_error(
		# 			description="User is not in players", error_code=await DebugLogger.report_internal_error("User is not in players")
		# 		),
		# 		ephemeral=True,
		# 	)
		# 	return

		if self.answering_player is not None:
			# 既に解答中のプレイヤーがいる場合はエラーメッセージを送信する
			await interaction.followup.send(
				embed=EmbedsTemplates.warning(
					title=t("msg.q.answering.title"),
					description=t("msg.q.answering.already.description", self.guild.get_member(self.answering_player.id)),
					icon="⚠️",
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 解答中プレイヤーを設定
		self.answering_player = self.get_player(user_id)
		# クイズに参加していないユーザーがクリックした場合はエラーメッセージを返す
		if self.answering_player is None:
			await interaction.followup.send(
				embed=EmbedsTemplates.error(description=t("view.q.answer_button.not_joined")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 部品を無効化
		# if interaction.view is not None:
		# 	interaction.view.disable_all_items()

		as_msg = await self.voice_channel.send(
			embed=EmbedsTemplates.info(
				title=t("msg.q.answering.title"),
				description=t("msg.q.answering.description", self.guild.get_member(user_id).mention),
				icon="💭",
			)
		)

		# 一時停止する
		self.ANSWERED.clear()
		logger.debug("- 一時停止")
		await self.pl.pause()

		# 解答の選択肢セレクターを送信する
		await interaction.followup.send(
			embed=EmbedsTemplates.info(title=t("msg.q.answer.title"), description=t("msg.q.answer.description"), icon="🗨️"),
			view=QuizAnswerSelectView(self.guild_id),
			delete_after=5,  # 5秒後に自動削除
			ephemeral=True,
		)

		try:
			# ユーザーが解答するまで最大5秒待機
			await asyncio.wait_for(self.ANSWERED.wait(), timeout=5.0)
		except TimeoutError:
			# タイムアウトした場合 (解答がなかった場合)
			logger.debug("- 解答なし: 不正解判定")
			if self.answering_player:
				self.answering_player.incorrect()
		finally:
			# 解答者をリセット (正解/不正解/タイムアウトいずれの場合も)
			self.answering_player = None
			await asyncio.sleep(1)
			# 正解が出ておらず、次の問題に進んでいない場合のみ再生を再開する
			if not self.NEXT.is_set():
				logger.debug("- 再生再開")
				await self.pl.pause(pause=False)

		# 解答中メッセージを削除
		await as_msg.delete()

		# 部品を有効化
		# if interaction.view is not None:
		# 	interaction.view.enable_all_items()

	async def answer(self, user_id: int, answer: str) -> bool | None:
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
		player = self.get_player(user_id)
		if player is None:
			await DebugLogger.report_internal_error("Player not found")
			# 解答者をリセット
			self.answering_player = None
			return None

		if self.pl.current.uri == answer:
			logger.debug("- 正解")
			# 正解
			player.correct()
			# 次の問題へ進む
			logger.debug("- 次の問題へ")
			# self.NEXT.set()
			await self.pl.stop()
			self.ANSWERED.set()
			return True
		# 不正解
		logger.debug("- 不正解")
		player.incorrect()
		self.ANSWERED.set()
		return False


@dataclass
class QuizSessionManager:
	"""クイズのセッションマネージャー"""

	sessions: dict[int, QuizSession] = field(default_factory=dict)

	def create_session(self, guild_id: int, channel_id: int, player: mafic.Player) -> QuizSession:
		"""セッションを新規作成"""
		logger.debug(f"セッション新規作成: {guild_id}/{channel_id}")
		self.sessions[guild_id] = QuizSession(guild_id, channel_id, player)
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
