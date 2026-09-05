import asyncio
import logging

import discord
from mogutune_core import Action, Mode
from pycord.localizer import t
from sonolink.models import Playable as SonoPlayable

from mogutune.chorus import YTMostReplayedAPI
from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.quiz.manager import quiz_session_manager
from mogutune.quiz.session import ready_threshold_met
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


class QuizReadyButtonView(discord.ui.View):
	"""準備完了ボタン (クイズ開始条件の投票)"""

	def __init__(self, session_id: int, *args: object, **kwargs: object) -> None:
		super().__init__(*args, timeout=None, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			logger.error("%s.session is None", self.__class__.__name__)
			return

		# 準備完了ボタン (ラベルに準備完了人数を表示)
		self.ready_button = discord.ui.Button(
			style=discord.ButtonStyle.green,
			label=self._label(0, len(self.session.roster.players)),
			emoji="✋",
		)
		self.ready_button.callback = self.ready_button_callback
		self.add_item(self.ready_button)

	def _label(self, votes: int, players: int) -> str:
		"""準備完了ボタンのラベルを生成する"""
		return t("view.q.ready_button.label") + f" ({votes}/{players})"

	# 準備完了ボタン
	async def ready_button_callback(self, interaction: discord.Interaction) -> None:
		logger.debug("準備完了ボタンクリック: %s", self.session_id)

		# 二重押し対策 (edit 反映前に再入した場合は無視する)
		if self.ready_button.disabled:
			return

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
				embed=EmbedsTemplates.error(description=t("view.q.ready_button.session_not_found")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# クイズに参加していないユーザーがクリックした場合はエラーメッセージを返す
		if not self.session.roster.is_joined(interaction.user.id):
			await interaction.response.send_message(
				embed=EmbedsTemplates.error(description=t("view.q.ready_button.not_joined")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 準備完了を宣言 (set なので重複は無視される)
		self.session.ready_votes.add(interaction.user.id)
		players = len(self.session.roster.players)
		votes = len(self.session.ready_votes)
		self.ready_button.label = self._label(votes, players)

		# 準備完了条件を満たした場合は開始する
		if ready_threshold_met(votes, players, self.session.ready_threshold):
			self.disable_all_items()
			try:
				await interaction.response.edit_message(view=self)
			except discord.errors.NotFound:
				pass
			self.session.READY.set()
			return

		try:
			await interaction.response.edit_message(view=self)
		except discord.errors.NotFound:
			pass


class QuizNextQButtonView(discord.ui.View):
	def __init__(self, session_id: int, disabled: bool = False, *args, **kwargs) -> None:
		super().__init__(timeout=None, *args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			logger.error("%s.session is None", self.__class__.__name__)
			return

		# 結果画面へ移行するため進行投票をリセットする (スキップ票が次の問題への投票を妨げないように)
		if self.session.vote_progression is not None:
			self.session.vote_progression.reset()

		# 次の問題があるかどうかに応じてラベルと絵文字を設定
		self._is_end = self.session.current_q_number >= self.session.q_tracks_count
		label, emoji = (t("view.q.next_q_button.label.next"), "⏭️") if not self._is_end else (t("view.q.next_q_button.label.end"), "🏁")
		# 投票モードでは初期から票数を表示する
		if self.session.progression_mode is Mode.VOTE:
			label += f" (0/{len(self.session.roster.players)})"

		self.next_q_button = discord.ui.Button(style=discord.ButtonStyle.primary, label=label, emoji=emoji, disabled=disabled)
		self.next_q_button.callback = self.next_q_button_callback
		self.add_item(self.next_q_button)

	# 次の問題ボタン
	async def next_q_button_callback(self, interaction: discord.Interaction) -> None:  # noqa: PLR0911
		logger.debug(f"次の問題ボタンクリック: {self.session_id}")

		# 二重押し対策 (edit 反映前に再入した場合は無視する)
		if self.next_q_button.disabled:
			return

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

		# 投票モード: 参加者全員が投票できる (過半数で可決)
		if self.session.progression_mode is Mode.VOTE:
			if not self.session.roster.is_joined(interaction.user.id):
				await interaction.response.send_message(
					embed=EmbedsTemplates.error(description=t("view.q.next_q_button.not_joined")),
					ephemeral=True,
					delete_after=3,
				)
				return
			vote_progression = self.session.vote_progression
			if vote_progression is None:
				await interaction.response.send_message(
					embed=EmbedsTemplates.internal_error(
						error_code=await DebugLogger.report_internal_error("next_q_button: vote_progression is None")
					),
					ephemeral=True,
					delete_after=3,
				)
				return
			vote_progression.vote(Action.NEXT, interaction.user.id)
			players = len(self.session.roster.players)
			votes = vote_progression.votes(Action.NEXT)
			self.next_q_button.label = (
				t("view.q.next_q_button.label.end") if self._is_end else t("view.q.next_q_button.label.next")
			) + f" ({votes}/{players})"
			if not vote_progression.should_advance(Action.NEXT, players):
				try:
					await interaction.response.edit_message(view=self)
				except discord.errors.NotFound:
					pass
				return
		# 主催者モード: クイズのオーナーだけがこのボタンを押せるようにする
		elif self.session.owner is not None and self.session.owner.id != interaction.user.id:
			await interaction.response.send_message(
				embed=EmbedsTemplates.error(
					description=t("view.q.next_q_button.do_not_have_permission"),
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 二重押しを防ぐためにボタンを無効化する (q_msg は次の問題で再利用するため削除しない)
		self.disable_all_items()
		try:
			await interaction.response.edit_message(view=self)
		except discord.errors.NotFound:
			pass
		# 再生停止 (=次の問題へ)
		self.session.expect_user_next = False
		try:
			await self.session.pl.stop()
		except Exception:
			logger.exception("- 再生停止エラー")
		self.session.NEXT.set()


class QuizAnswerSelectView(discord.ui.View):
	def __init__(self, session_id: int, answer_tracks: list[SonoPlayable], *, with_author: bool = False, **kwargs) -> None:
		super().__init__(**kwargs)

		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			logger.error("%s.session is None", self.__class__.__name__)
			return

		logger.debug("Answer Select Options")
		for at in answer_tracks:
			logger.debug(f"{at.title}: {at.uri}")

		self.answer_select = discord.ui.Select(discord.ComponentType.string_select)
		# 解答候補一覧 (uri がないトラックは SelectOption の value にできないため除外)
		for tr in answer_tracks:
			if tr.uri is None:
				continue
			_title = self.session.format_track_title(tr, max_length=90, with_author=with_author)
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
			return

		result = await self.session.answer(interaction.user.id, interaction.data["values"][0])

		# 選択肢セレクターを即削除して選択し直しを防ぐ
		await interaction.response.defer()
		try:
			await interaction.delete_original_response()
		except discord.errors.NotFound:
			pass

		# 不正解
		# FIXME: 解答判定時に問題があった場合も None が返ってきて不正解判定になるので、問題があった場合は別の処理を行うようにする
		if result is None:
			_track = self.session.get_track_from_uri(interaction.data["values"][0])
			_title = self.session.format_track_title(_track)
			# 不正解を q_msg に表示する (全員に見える)
			await self.session._edit_q_msg(  # noqa: SLF001
				EmbedsTemplates.error(
					title=t("view.q.answer_select.incorrect.title"),
					description=t("view.q.answer_select.incorrect.description", _title),
					icon="❌",
				)
			)
			# SFX
			await self.session.play_sfx(SFX.INCORRECT)
			await asyncio.sleep(1)
		# 正解
		else:
			_track = result
			_title = self.session.format_track_title(_track, with_author=True)
			_embed = self.session.set_track_artwork(
				EmbedsTemplates.success(
					title=t("view.q.answer_select.correct.title"),
					description=t("view.q.answer_select.correct.description", interaction.user.mention, _title, _track.uri),
					icon="✅",
				),
				_track,
			)
			_embed = self.session.set_footer_track_info(_embed, _track)

			# q_msg を正解 embed に編集し、次の問題へボタンを配置する
			next_q_button = QuizNextQButtonView(self.session_id, disabled=True)
			await self.session._edit_q_msg(_embed, view=next_q_button)  # noqa: SLF001
			# SFX
			await self.session.play_sfx(SFX.CORRECT, restore=False)  # restore を False にして解答できないままにする
			await asyncio.sleep(1)

			# 答えの楽曲を再生する (終了時間を None にして最後まで再生する)
			# ソースが YouTube の場合は YTMostReplayedAPI からリプレイ回数が最も多い部分を取得してそこから再生する
			# if self.session.pl.current is not None and self.session.pl.current.uri is not None:
			logger.debug("- 正解後再生開始")
			# リプレイ終了は次ボタン待ちにする (自然終了での自動進行を防ぐ)
			self.session.expect_user_next = True
			try:
				_position = 0
				_uri = await self.session.resolve_youtube_track_uri(_track)
				if _uri is None:
					_uri = _track.uri
				if _uri is not None and ("youtube.com" in _uri or "youtu.be" in _uri):
					_position = await YTMostReplayedAPI.get_chorus_info(_uri)
					logger.info("Play Position: %s", _position)
					if _position is None:
						_position = 0
				logger.debug("Resuming track: %s at %s", _track.uri, _position)
				await self.session.pl.play(_track, start=_position, volume=self.session.PL_VOLUME, paused=False)
			except Exception:
				logger.exception("正解後の楽曲再生に失敗しました")
				self.session.NEXT.set()

			# 次の問題へボタンを有効化
			next_q_button.enable_all_items()
			await self.session._edit_q_msg_view(next_q_button)  # noqa: SLF001


class QuizAnswerButtonView(discord.ui.View):
	def __init__(self, session_id: int, *args, **kwargs) -> None:
		super().__init__(timeout=None, *args, **kwargs)
		self.session_id = session_id
		self.session = quiz_session_manager.get_session(session_id)

		# セッションが存在するかチェック
		if self.session is None:
			logger.error("%s.session is None", self.__class__.__name__)
			return

		# 解答ボタン
		self.answer_button = discord.ui.Button(style=discord.ButtonStyle.green, label=t("view.q.answer_button.label"), emoji="💭")
		self.answer_button.callback = self.answer_button_callback
		self.add_item(self.answer_button)

		# 問題スキップボタン
		self.skip_button = discord.ui.Button(style=discord.ButtonStyle.gray, label=t("view.q.skip_button.label"), emoji="⏭️")
		# 投票モードでは初期から票数を表示する
		if self.session.progression_mode is Mode.VOTE:
			self.skip_button.label += f" (0/{len(self.session.roster.players)})"
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
	async def skip_button_callback(self, interaction: discord.Interaction) -> None:  # noqa: PLR0911, PLR0915
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

		# 楽曲を再生していない場合はエラーメッセージを返す (モード共通)
		if self.session.pl.current is None:
			await interaction.respond(
				embed=EmbedsTemplates.error(description=t("view.q.skip_button.not_playing")),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 解答ができない状態の場合はエラーメッセージを送信する (モード共通)
		if not self.session.can_answered or self.session.answering_player is not None:
			await interaction.respond(
				embed=EmbedsTemplates.warning(
					description=t("view.q.skip_button.cannot_skipped"),
				),
				ephemeral=True,
				delete_after=3,
			)
			return

		# 投票モード: 参加者全員が投票できる (過半数で可決)
		if self.session.progression_mode is Mode.VOTE:
			if not self.session.roster.is_joined(interaction.user.id):
				await interaction.response.send_message(
					embed=EmbedsTemplates.error(description=t("view.q.skip_button.not_joined")),
					ephemeral=True,
					delete_after=3,
				)
				return
			vote_progression = self.session.vote_progression
			if vote_progression is None:
				await interaction.response.send_message(
					embed=EmbedsTemplates.internal_error(
						error_code=await DebugLogger.report_internal_error("skip_button: vote_progression is None")
					),
					ephemeral=True,
					delete_after=3,
				)
				return
			vote_progression.vote(Action.SKIP, interaction.user.id)
			players = len(self.session.roster.players)
			votes = vote_progression.votes(Action.SKIP)
			self.skip_button.label = t("view.q.skip_button.label") + f" ({votes}/{players})"
			if not vote_progression.should_advance(Action.SKIP, players):
				try:
					await interaction.response.edit_message(view=self)
				except discord.errors.NotFound:
					pass
				return
		# 主催者モード: クイズのオーナーだけがこのボタンを押せるようにする
		else:
			if self.session.owner is not None and self.session.owner.id != interaction.user.id:
				await interaction.respond(
					embed=EmbedsTemplates.error(
						description=t("view.q.skip_button.do_not_have_permission"),
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
		_title = self.session.format_track_title(_track, with_author=True)
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
		await interaction.response.defer()
		await self.session._edit_q_msg(_embed, view=next_q_button)  # noqa: SLF001

		# 答えの楽曲を再生する
		# ソースが YouTube の場合は YTMostReplayedAPI からリプレイ回数が最も多い部分を取得してそこから再生する
		if self.session.pl.current is not None and self.session.pl.current.uri is not None:
			logger.debug("- スキップ後再生開始")
			# リプレイ終了は次ボタン待ちにする (自然終了での自動進行を防ぐ)
			self.session.expect_user_next = True
			try:
				_position = 0
				_uri = await self.session.resolve_youtube_track_uri(self.session.pl.current)
				if _uri is None:
					_uri = self.session.pl.current.uri
				if _uri is not None and ("youtube.com" in _uri or "youtu.be" in _uri):
					_position = await YTMostReplayedAPI.get_chorus_info(_uri)
					logger.info("Play Position: %s", _position)
					if _position is None:
						_position = 0
				logger.debug("Resuming track (Skip): %s at %s", pl_current.uri, _position)
				await self.session.pl.play(pl_current, start=_position, volume=self.session.PL_VOLUME, paused=False)
			except Exception:
				logger.exception("スキップ後の楽曲再生に失敗しました")
				self.session.NEXT.set()

		# 次の問題へボタンを有効化
		next_q_button.enable_all_items()
		await self.session._edit_q_msg_view(next_q_button)  # noqa: SLF001
