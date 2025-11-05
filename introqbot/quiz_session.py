import asyncio
import logging
import random
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord
import mafic
from pycord.localizer import t

from introqbot.client import client
from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates

if TYPE_CHECKING:
	from introqbot.quiz_session import QuizSession

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


class QuizNextQButtonView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)  # コールバックでNoneチェックするのでここではそのまま

		self.next_q_button = discord.ui.Button(style=discord.ButtonStyle.primary, label=t("view.q.next_q_button.label"), emoji="⏭️")
		self.next_q_button.callback = self.next_q_button_callback
		self.add_item(self.next_q_button)

	# 解答ボタン
	async def next_q_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"次の問題ボタンクリック: {self.session_id}")

		self.session = quiz_session_manager.get_session(self.session_id)
		# セッションが存在するかチェック
		if self.session is None:
			await interaction.respond(embed=EmbedsTemplates.error(description=t("view.q.join.msg.session_not_found")), ephemeral=True)
			return

		if interaction.message is None:
			_ = await interaction.response.send_message(
				embed=EmbedsTemplates.internal_error(
					error_code=await DebugLogger.report_internal_error("QuizNextQButtonView.interaction.message is None")
				)
			)
			# 削除対象メッセージに追加
			if _.message is not None:
				self.session.next_cleanup_messages.append(_.message)
			return

		# TODO: クイズのオーナーだけがこのボタンを押せるようにする？

		# 正解メッセージを削除する
		try:
			await interaction.message.delete()
		except discord.errors.NotFound:
			pass
		# 再生停止 (=次の問題へ)
		await self.session.pl.stop()


class QuizAnswerSelectView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)

		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		if self.session is None:
			logger.warning("QuizAnswerSelectView.session is None on init")
			return

		logger.debug("Generating Answer Select Options")
		for at in self.session.get_answer_tracks():
			logger.debug(f"{at.title}: {at.uri}")

		self.answer_select = discord.ui.Select(discord.ComponentType.string_select)
		# 解答候補一覧
		for tr in self.session.get_answer_tracks():
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

		self.session = quiz_session_manager.get_session(self.session_id)
		# セッションが存在するかチェック
		if self.session is None or interaction.message is None:
			await interaction.response.send_message(
				embed=EmbedsTemplates.error(description=t("view.q.join.msg.session_not_found")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# クリックしたユーザーが解答権を持っていない場合はエラーメッセージを返す
		if self.session.answering_player is not None and self.session.answering_player.id != interaction.user.id:
			await interaction.response.send_message(
				embed=EmbedsTemplates.error(description=t("view.q.answer_select.do_not_have_permission.description")),
				ephemeral=True,
				delete_after=3,
			)
			return

		result = await self.session.answer(interaction.user.id, interaction.data["values"][0])

		# 不正解
		# FIXME: 解答判定時に問題があった場合も None が返ってきて不正解判定になるので、問題があった場合は別の処理を行うようにする
		if result is None:
			await interaction.response.send_message(
				embed=EmbedsTemplates.error(
					title=t("view.q.answer_select.incorrect.title"),
					description=t(
						"view.q.answer_select.incorrect.description", self.session.get_track_from_uri(interaction.data["values"][0]).title
					),
					icon="❌",
				),
				ephemeral=True,
				delete_after=2,
			)
		# 正解
		else:
			correct_msg = await interaction.response.send_message(
				embed=EmbedsTemplates.success(
					title=t("view.q.answer_select.correct.title"),
					description=t("view.q.answer_select.correct.description", result.title),
					icon="✅",
				),
				view=QuizNextQButtonView(self.session_id),  # 次の問題へ ボタン
				# ephemeral=True,
				# delete_after=3,
			)
			# 削除対象メッセージに追加
			self.session.add_cleanup_message(correct_msg.message)


class QuizAnswerButtonView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		self.answer_button = discord.ui.Button(style=discord.ButtonStyle.primary, label=t("view.q.answer_button.label"), emoji="💭")
		self.answer_button.callback = self.answer_button_callback
		self.add_item(self.answer_button)

	# 解答ボタン
	async def answer_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug(f"解答ボタンクリック: {self.session_id}")

		await interaction.response.defer()

		self.session = quiz_session_manager.get_session(self.session_id)
		# セッションが存在するかチェック
		if self.session is None:
			# セッションが見つからない場合はエラーメッセージを送信する
			await interaction.respond(
				embed=EmbedsTemplates.error(description=t("view.q.join.msg.session_not_found")),
				ephemeral=True,
				delete_after=3,
			)
			return

		if not self.session.can_answered:
			# 解答ができない状態の場合はエラーメッセージを送信する
			await interaction.respond(
				embed=EmbedsTemplates.warning(
					description=t("view.q.answer_button.cannot_answered"),
				),
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

	pl: "QuizPlayerNode"
	"""プレイヤー (Mafic)"""

	players: dict[int, QuizPlayer] = field(default_factory=dict)
	"""参加するプレイヤーの一覧"""
	queue: list[int] = field(default_factory=list)
	"""参加待ちのプレイヤーのID"""
	playing: bool = False
	"""クイズが開始されているかどうか"""

	answering_player: QuizPlayer | None = None
	"""現在解答中のプレイヤー"""
	current_q_number: int = 0
	"""問題番号"""
	q_original_tracks: list[mafic.Track] = field(default_factory=list)
	"""問題の元のトラック一覧"""
	q_tracks: list[mafic.Track] | None = None
	"""問題のトラック一覧"""

	next_cleanup_messages: list[discord.Message] = field(default_factory=list)
	"""次の問題開始時に削除するメッセージのリスト"""

	can_answered: bool = False
	"""解答ができる状態かどうか"""

	NEXT: asyncio.Event = field(default_factory=asyncio.Event)
	ANSWERED: asyncio.Event = field(default_factory=asyncio.Event)

	def add_player(self, user_id: int) -> None:
		"""プレイヤーを追加"""
		if self.is_player_joined(user_id):
			return
		logger.debug(f"プレイヤー追加: {user_id}")
		self.players[user_id] = QuizPlayer(user_id)

	def remove_player(self, user_id: int) -> None:
		"""プレイヤーを削除"""
		if not self.is_player_joined(user_id):
			return
		logger.debug(f"プレイヤー削除: {user_id}")
		del self.players[user_id]

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
		return user_id in self.players

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
		return self.players.get(user_id)

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
		for player in self.players.values():
			player.incorrect_reset()

	def reset(self) -> None:
		"""クイズセッションをリセット"""
		# 全プレイヤーのポイントと不正解フラグをリセット
		for player in self.players.values():
			player.reset()
		self.players.clear()
		self.queue.clear()
		self.next_cleanup_messages.clear()

		# 各変数をリセット
		self.q_original_tracks = []
		self.q_tracks = []
		self.answering_player = None

	async def play(self, tracks: mafic.Playlist, q_count: int) -> bool | str:
		"""クイズのメインループを実行する"""
		try:
			self.playing = True
			self.reset()

			if not await self._initialize_quiz(tracks, q_count):
				return False

			await self._run_quiz_loop(tracks.name, q_count)

			await self._finalize_quiz()
			return True
		except Exception:
			return await DebugLogger.report_internal_error(traceback.format_exc())

	async def _initialize_quiz(self, tracks: mafic.Playlist, q_count: int) -> bool:
		"""クイズの初期設定とバリデーションを行う"""
		self.guild = client.get_guild(self.guild_id)
		self.voice_channel = self.guild.get_channel(self.channel_id) if self.guild else None
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
		self.q_tracks = random.sample(self.q_original_tracks, len(self.q_original_tracks))[:q_count]

		if isinstance(self.voice_channel, discord.VoiceChannel):
			# 楽曲数が2曲未満の場合はエラーメッセージを返す
			if len(self.q_original_tracks) < 2:
				await self.voice_channel.send(embed=EmbedsTemplates.error(description=t("msg.q.init.must_be_at_least_two_songs")))
				# 終了
				return False

			# 有効なトラック数が問題数よりも少ない場合はエラーメッセージを返す
			if len(self.q_original_tracks) < q_count:
				await self.voice_channel.send(
					embed=EmbedsTemplates.error(description=t("msg.q.init.not_enough_song", len(self.q_original_tracks), q_count))
				)
				return False

		logger.debug(f"クイズ開始: {self.guild_id}/{self.channel_id}")
		return True

	async def _run_quiz_loop(self, playlist_name: str, q_count: int) -> None:
		"""クイズの問題ループを実行する"""
		if not isinstance(self.voice_channel, discord.VoiceChannel):
			return
		# プレイヤー一覧テキストを生成
		player_list_text = await self._get_player_mentions_text()
		# クイズ開始メッセージを送信
		start_msg = await self.voice_channel.send(
			embed=EmbedsTemplates.info(
				title=t("msg.q.init.title"),
				description=t("msg.q.init.description", playlist_name, q_count, player_list_text),
				icon="▶️",
			)
		)

		q_msg = None
		for i, q in enumerate(self.q_tracks, 1):
			if not self.playing:  # stopコマンドなどで停止された場合
				break

			logger.debug(f"{i}問目")

			# プレイヤー一覧テキストを更新する
			player_list_text = await self._get_player_mentions_text()
			start_msg.embeds[0].description = t("msg.q.init.description", playlist_name, q_count, player_list_text)
			await start_msg.edit(embed=start_msg.embeds[0])

			self.NEXT.clear()

			# 問題開始メッセージを送信
			q_msg = await self.voice_channel.send(
				embed=EmbedsTemplates.info(title=t("msg.q.start.title", str(i)), description=t("msg.q.start.description"), icon="❔"),
				view=QuizAnswerButtonView(self.guild_id),  # 回答ボタン
			)
			# 参加待ちのプレイヤーを参加させる
			self.join_queued_players()

			# 解答ができる状態にする
			self.can_answered = True

			logger.debug("再生開始")

			# 再生
			await self.pl.play(q)
			await self.NEXT.wait()  # 待機
			await self.pl.pause()  # 念の為一時停止

			# 解答ができない状態にする
			self.can_answered = False

			logger.debug("再生終了")
			# ラウンド終了時のメッセージ削除など
			await self._cleanup_round()

			# 待機
			logger.debug("待機")
			await asyncio.sleep(3)

			# 解答メッセージを削除
			if q_msg:
				await q_msg.delete()

	async def _finalize_quiz(self) -> None:
		"""クイズを終了し、結果を表示する"""
		if not isinstance(self.voice_channel, discord.VoiceChannel):
			return
		# ランキングテキストを生成
		# TODO: ただの一覧ではなく順位をつけて表示するようにする
		ranking_text = await self._get_ranking_text()
		# 終了メッセージを送信する
		await self.voice_channel.send(
			embed=EmbedsTemplates.info(title=t("msg.q.end.title"), description=t("msg.q.end.description", ranking_text), icon="🏁")
		)

		# 終了
		self.playing = False
		self.reset()

	async def _get_player_mentions_text(self) -> str:
		"""参加プレイヤーのメンションリスト文字列を生成する"""
		if not self.guild:
			return ""
		player_mentions = []
		for p_id in self.players:
			member = self.guild.get_member(p_id) or await self.guild.fetch_member(p_id)
			if member:
				player_mentions.append(member.mention)
		return "  - " + "\n  - ".join(player_mentions) if player_mentions else t("msg.q.init.no_players")

	async def _get_ranking_text(self) -> str:
		"""ランキング文字列を生成する"""
		if not self.guild:
			return ""
		# TODO: 順位付け
		ranking_list = []
		for p in self.players.values():
			member = self.guild.get_member(p.id) or await self.guild.fetch_member(p.id)
			if member:
				ranking_list.append(f"{member.mention}: `{p.point}`")
		return "- " + "\n- ".join(ranking_list) if ranking_list else t("msg.q.init.no_players")

	async def _cleanup_round(self) -> None:
		"""ラウンド終了時のクリーンアップ処理"""
		await self._cleanup_messages()
		self.refresh()

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
					description=t(
						"msg.q.answering.already.description",
						(
							self.guild.get_member(self.answering_player.id) or await self.guild.fetch_member(self.answering_player.id)
						).mention,
					),
					icon="⚠️",
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 解答ができない状態にする
		self.can_answered = False

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
				description=t(
					"msg.q.answering.description", (self.guild.get_member(user_id) or await self.guild.fetch_member(user_id)).mention
				),
				icon="💭",
			)
		)
		self.add_cleanup_message(as_msg)

		# 一時停止する
		self.ANSWERED.clear()
		logger.debug("- 一時停止")
		await self.pl.pause()

		# 解答の選択肢セレクターを送信する
		selector_msg = await interaction.followup.send(
			embed=EmbedsTemplates.info(title=t("msg.q.answer.title"), description=t("msg.q.answer.description"), icon="🗨️"),
			view=QuizAnswerSelectView(self.guild_id),
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
		try:
			await as_msg.delete()
		except discord.errors.NotFound:
			pass

		# 部品を有効化
		# if interaction.view is not None:
		# 	interaction.view.enable_all_items()

	def add_cleanup_message(self, message: discord.Message | None) -> None:
		"""次のラウンドで削除するメッセージを追加する"""
		if message:
			self.next_cleanup_messages.append(message)

	async def _cleanup_messages(self) -> None:
		"""ラウンド終了時に不要なメッセージを削除する"""
		for msg in self.next_cleanup_messages:
			try:
				await msg.delete()
			except discord.errors.NotFound:
				pass  # 既に削除されている
			except Exception as e:
				logger.error(f"問題終了時メッセージクリーンアップエラー: {e}")
		self.next_cleanup_messages.clear()

	async def answer(self, user_id: int, answer: str) -> mafic.Track | None:
		"""解答する"""
		logger.debug(f"解答判定: {user_id} - {answer}")
		if self.pl is None:
			await DebugLogger.report_internal_error("Session.player is None")
			return None
		if self.pl.current is None:
			await DebugLogger.report_internal_error("Session.player.current is None")
			return None
		if not self.is_player_joined(user_id):
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
			# 解答ができない状態にする
			self.can_answered = False
			correct_track = self.pl.current
			# 正解
			player.correct()
			await asyncio.sleep(1)
			# 答えの楽曲を再生する (終了時間を None にして最後まで再生する)
			await self.pl.update(position=0, end_time=None, pause=False)
			# 次の問題へ進む
			# logger.debug("- 次の問題へ")
			# self.NEXT.set()
			# await self.pl.stop()
			self.ANSWERED.set()
			return correct_track
		# 不正解
		logger.debug("- 不正解")
		player.incorrect()
		self.ANSWERED.set()
		# 解答ができる状態にする
		self.can_answered = True
		return None


class QuizPlayerNode(mafic.Player):
	"""クイズセッション情報を持つPlayerクラス"""

	def __init__(self, client: discord.Client, channel: discord.VoiceChannel) -> None:
		super().__init__(client, channel)
		self.quiz_session: QuizSession | None = None


@dataclass
class QuizSessionManager:
	"""クイズのセッションマネージャー"""

	sessions: dict[int, QuizSession] = field(default_factory=dict)

	def create_session(self, guild_id: int, channel_id: int, player: QuizPlayerNode) -> QuizSession:
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
		session.add_queue(member.id)
	# クイズが行われているボイスチャンネルから退出した
	elif before.channel is not None and after.channel is None and before.channel.id == session.channel_id:
		# プレイヤーから削除する
		session.remove_player(member.id)
		session.remove_queue(member.id)


# 再生開始時イベント
@client.listen()
async def on_track_start(event: mafic.TrackStartEvent) -> None:
	if not isinstance(event.player, QuizPlayerNode):
		return
	guild_id = event.player.guild.id
	logger.debug(f"再生開始イベント: {guild_id}")


# 再生終了時イベント
@client.listen()
async def on_track_end(event: mafic.TrackEndEvent) -> None:
	if not isinstance(event.player, QuizPlayerNode):
		return
	session = event.player.quiz_session
	if session is None:
		return
	# 次の問題へ進む
	session.NEXT.set()
