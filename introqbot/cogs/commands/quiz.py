import asyncio
import logging
import traceback

import discord
import mafic
from discord.ext import commands
from pycord.localizer import t

from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.presets import PlaylistPresets
from introqbot.quiz_session import prepare_play, quiz_session_manager

logger = logging.getLogger(__name__)


class QuizCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def play(
		self,
		ctx: discord.ApplicationContext,
		query: discord.Option(str, required=False, default=""),  # pyright: ignore[reportInvalidTypeForm]
		preset: discord.Option(
			input_type=str,
			required=False,
			choices=PlaylistPresets.get_presets(),
		),  # pyright: ignore[reportInvalidTypeForm]
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
		await prepare_play(ctx.interaction, ctx.user, ctx.guild, query, preset, q_count)

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
			await quiz_session_manager.end_session(session.guild_id)
			await ctx.respond(
				embed=EmbedsTemplates.success(description=t("cmd.end.ended", ctx.guild.get_channel(session.channel_id).mention)),
				ephemeral=True,
			)
		else:
			await ctx.respond(embed=EmbedsTemplates.error(description=t("cmd.end.quiz_not_started")), ephemeral=True)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(QuizCommands(bot))
