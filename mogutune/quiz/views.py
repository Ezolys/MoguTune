import asyncio
import logging

import discord
import mafic
from pycord.localizer import t

from mogutune.chorus import YTMostReplayedAPI
from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.quiz.manager import quiz_session_manager
from mogutune.sfx import SFX

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
		from mogutune.quiz.prepare import prepare_play  # noqa: PLC0415

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

	# 次の問題ボタン
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
			_title = self.session.format_track_title(tr, max_length=90)
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
			_track = self.session.get_track_from_uri(interaction.data["values"][0])
			_title = self.session.format_track_title(_track)
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
			_track = result
			_title = self.session.format_track_title(_track)
			_embed = self.session.set_track_artwork(
				EmbedsTemplates.success(
					title=t("view.q.answer_select.correct.title"),
					description=t("view.q.answer_select.correct.description", interaction.user.mention, _title, _track.uri),
					icon="✅",
				),
				_track,
			)
			_embed = self.session.set_footer_track_info(_embed, _track)

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
		_title = self.session.format_track_title(_track)
		_embed = self.session.set_track_artwork(
			EmbedsTemplates.info(
				title=t("msg.q.skip.title"),
				description=t("msg.q.skip.description", _title, _track.uri),
				icon="⏭️",
			),
			_track,
		)
		_embed = self.session.set_footer_track_info(_embed, _track)

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
