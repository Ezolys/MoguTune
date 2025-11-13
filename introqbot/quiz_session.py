import asyncio
import datetime
import logging
import random
import traceback
from dataclasses import dataclass, field

import discord
import mafic
from pycord.localizer import t

from introqbot.client import client
from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.songle import SongleAPI

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

		# セッションを取得する
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
		await session.join_player(interaction.user.id)

		await interaction.respond(embed=EmbedsTemplates.success(description=t("view.q.join.msg.joined")), ephemeral=True)


class QuizNextQButtonView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(timeout=None, *args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			asyncio.run(DebugLogger.report_internal_error("QuizAnswerSelectView.session is None"))
			return

		self.next_q_button = discord.ui.Button(style=discord.ButtonStyle.primary, label=t("view.q.next_q_button.label"), emoji="⏭️")
		self.next_q_button.callback = self.next_q_button_callback
		self.add_item(self.next_q_button)

	# 解答ボタン
	async def next_q_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"次の問題ボタンクリック: {self.session_id}")

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
			if _.message is not None:
				self.session.next_cleanup_messages.append(_.message)
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
			).set_thumbnail(url=_track.artwork_url)  # ジャケットを設定
			logger.info(_track.artwork_url)
			# メッセージを送信
			_ = await interaction.response.send_message(
				embed=_embed,
				view=QuizNextQButtonView(self.session_id),  # 次の問題へ ボタン
				# ephemeral=True,
				# delete_after=3,
			)
			# 削除対象メッセージに追加
			if _.message is not None:
				self.session.next_cleanup_messages.append(_.message)


class QuizAnswerButtonView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(timeout=None, *args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			asyncio.run(DebugLogger.report_internal_error("QuizAnswerSelectView.session is None"))
			return

		self.answer_button = discord.ui.Button(style=discord.ButtonStyle.primary, label=t("view.q.answer_button.label"), emoji="💭")
		self.answer_button.callback = self.answer_button_callback
		self.add_item(self.answer_button)

	# 解答ボタン
	async def answer_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"解答ボタンクリック: {self.session_id}")

		await interaction.response.defer()

		# セッションを取得し直す
		self.session = quiz_session_manager.get_session(self.session_id)

		# セッションが存在するかチェック
		if self.session is None:
			# セッションが見つからない場合はエラーメッセージを送信する
			await interaction.respond(
				embed=EmbedsTemplates.error(description=t("view.q.answer_button.session_not_found")),
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
	PL_VOLUME: int = 10
	"""プレイヤーのボリューム"""

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
	q_original_tracks: list[mafic.Track] | None = None
	"""問題の元のトラック一覧"""
	q_tracks: list[mafic.Track] | None = None
	"""問題のトラック一覧"""

	next_cleanup_messages: list[discord.Message] = field(default_factory=list)
	"""次の問題開始時に削除するメッセージのリスト"""

	can_answered: bool = False
	"""解答ができる状態かどうか"""

	NEXT: asyncio.Event = field(default_factory=asyncio.Event)
	ANSWERED: asyncio.Event = field(default_factory=asyncio.Event)

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
		self.current_q_number = 0
		self.q_start_time = None
		self.answering_player = None
		self.owner = None

	async def end(self) -> None:
		"""クイズを終了する"""
		self.playing = False
		try:
			await self.pl.stop()
		except Exception:
			logger.error("- 再生終了エラー")
			logger.error(traceback.format_exc())

		try:
			logger.debug("ランキング生成")
			# ランキングテキストを生成
			# TODO: ただの一覧ではなく順位をつけて表示するようにする
			if len(self.players) == 0:  # プレイヤーが0人の場合は専用のメッセージを設定
				ranking_list = [t("msg.q.end.no_players")]
			else:
				ranking_list = []
				for p in self.players:
					member = await self.guild.get_or_fetch(discord.Member, p.id)
					pn = "Unknown"
					if member is not None:
						pn = member.mention or member.display_name
					ranking_list.append(f"{pn}: `{p.point}`")
			# 結合
			ranking = "- " + "\n- ".join(ranking_list)

			# 終了メッセージを送信する
			await self.voice_channel.send(
				embed=EmbedsTemplates.info(title=t("msg.q.end.title"), description=t("msg.q.end.description", ranking), icon="🏁")
			)
		except Exception:
			logger.error("- 終了メッセージ送信/ランキング生成エラー")
			logger.error(traceback.format_exc())

		# セッションを削除する
		quiz_session_manager.delete_session(self.guild_id)

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

				self.q_number = i

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
				await asyncio.sleep(2)

			# 解答メッセージを削除
			try:
				await q_msg.delete()
			except discord.errors.NotFound:
				pass

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

		# 一時停止する
		self.ANSWERED.clear()
		logger.debug("- 一時停止")
		await self.pl.pause()

		# 全プレイヤーの不正解フラグをリセット
		self.refresh()

		# 解答の選択肢セレクターを送信する
		_ = await interaction.followup.send(
			embed=EmbedsTemplates.info(title=t("msg.q.answer.title"), description=t("msg.q.answer.description"), icon="🗨️"),
			view=QuizAnswerSelectView(self.guild_id, await self.get_answer_tracks()),
			delete_after=5,  # 5秒後に自動削除
			ephemeral=True,
			wait=True,
		)

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
			await asyncio.sleep(1)
			# 答えの楽曲を再生する (終了時間を None にして最後まで再生する)
			logger.debug("- 正解後再生開始")
			_position = 0.0
			# ソースが YouTube の場合は Songle API からサビの位置を取得してそこから再生する
			if self.pl.current.source == "youtube" and self.pl.current.uri is not None:
				_position = await SongleAPI.get_chorus_info(self.pl.current.uri)
				if _position is not None and _position > 0:
					_position -= 500  # 0.5秒前
				else:
					_position = 0.0
			await self.pl.update(position=_position, end_time=None, volume=self.PL_VOLUME, pause=False)
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

	def create_session(self, guild_id: int, channel_id: int, player: mafic.Player) -> QuizSession:
		"""セッションを新規作成する"""
		logger.debug(f"セッション新規作成: {guild_id}/{channel_id}")
		self.sessions[guild_id] = QuizSession(guild_id, channel_id, player)
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
	logger.debug(f"再生終了イベント: {guild_id}")
	session = quiz_session_manager.get_session(guild_id)
	if session is None:
		return
	# 次の問題へ進む
	session.NEXT.set()
