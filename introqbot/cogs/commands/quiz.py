import logging
from typing import get_args

import discord
from discord.ext import commands
from pycord.localizer import Locale, t

from introqbot.db import DBManager
from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.quiz_session import prepare_play, quiz_session_manager

logger = logging.getLogger(__name__)


class QuizCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	preset_list: list
	preset_choices: dict[str, list[discord.OptionChoice]]

	async def load_presets(self) -> None:
		logger.info("プレイリストプリセットを読み込み")

		# データーベースから最新のプリセットを取得して整形する
		presets = await DBManager.col_presets.find().to_list(length=100)
		self.preset_list = presets

		# 各言語の OptionChoice のリストを作成
		self.preset_choices = {}
		for lang_code in get_args(Locale):
			self.preset_choices[lang_code] = []
			for info in self.preset_list:
				title = ""
				desc = ""
				title_desc = ""
				if info.get("title_" + lang_code) is not None and info.get("description_" + lang_code) is not None:
					title = info.get("title_" + lang_code)
					desc = info.get("description_" + lang_code)
				else:
					title = info.get("title_" + "en-GB")
					desc = info.get("description_" + "en-GB")
				# 説明文が設定されていない場合はセパレーターを除いてタイトルのみにする
				title_desc = f"{title} | {desc}" if desc != "" and desc is not None else title
				# URL が設定されている場合のみ一覧へ追加する
				if "url" in info and info.get("url") is not None:
					self.preset_choices[lang_code].append(discord.OptionChoice(name=title_desc, value=info.get("url")))

	async def get_presets(self, ctx: discord.AutocompleteContext) -> list[discord.OptionChoice]:
		"""プレイリストのプリセットをDiscordのコマンドオプションの選択肢として取得する"""
		# 入力内容が0文字の場合のみ一覧を返す
		# インタラクションの言語に合わせて一覧を取得する 存在しない場合は英語のを返す
		if ctx.value == "":
			return self.preset_choices.get(ctx.interaction.locale or "en-GB", self.preset_choices["en-GB"])
		return []

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def play(
		self,
		ctx: discord.ApplicationContext,
		query: discord.Option(str, required=True, autocomplete=get_presets),  # pyright: ignore[reportInvalidTypeForm]
		# preset: discord.Option(
		# 	str,
		# 	required=False,
		# 	autocomplete=get_presets,
		# ),  # pyright: ignore[reportInvalidTypeForm]
		# search_type: discord.Option(
		# 	input_type=str,
		# 	required=False,
		# 	default=mafic.SearchType.YOUTUBE.name,
		# 	choices=[
		# 		discord.OptionChoice("Spotify", mafic.SearchType.SPOTIFY_SEARCH.name),
		# 		discord.OptionChoice("YouTube", mafic.SearchType.YOUTUBE.name),
		# 	],
		# ),  # pyright: ignore[reportInvalidTypeForm]
		q_count: discord.Option(int, min_value=1, max_value=50, required=False, default=10),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		if ctx.guild is None:
			logger.error("Guild is None")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=await DebugLogger.report_internal_error("QuizCommands.play - ctx.guild is None")
				)
			)
			return
		if ctx.channel is None:
			logger.error("Channel is None")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(
					error_code=await DebugLogger.report_internal_error("QuizCommands.play - ctx.channel is None")
				)
			)
			return

		# クイズを開始
		await prepare_play(ctx.interaction, ctx.user, ctx.guild, query, q_count)

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def end(self, ctx: discord.ApplicationContext) -> None:
		if ctx.guild is None:
			logger.error("Guild is None")
			raise Exception("Guild is None")

		session = quiz_session_manager.get_session(ctx.guild.id)
		if session:
			# 実行者がクイズの主催者かチェック
			if session.owner is not None and session.owner.id != ctx.user.id:
				await ctx.respond(
					embed=EmbedsTemplates.error(
						description=t("cmd.end.do_not_have_permission"),
					),
					ephemeral=True,
				)
				return
			# クイズを強制終了する
			await session.end()
			await ctx.respond(
				embed=EmbedsTemplates.success(description=t("cmd.end.ended", ctx.guild.get_channel(session.channel_id).mention)),
				ephemeral=True,
			)
		else:
			await ctx.respond(embed=EmbedsTemplates.error(description=t("cmd.end.quiz_not_started")), ephemeral=True)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(QuizCommands(bot))
