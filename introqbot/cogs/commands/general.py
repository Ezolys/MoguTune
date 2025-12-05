import datetime
import logging
import traceback
from os import getenv

import discord
from discord.ext import commands
from pycord.localizer import t

from introqbot.app import App
from introqbot.client import client
from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.quiz_session import quiz_session_manager

logger = logging.getLogger(__name__)


class GeneralCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def ping(self, ctx: discord.ApplicationContext) -> None:
		ping = round(client.latency * 1000)
		await ctx.respond(embed=EmbedsTemplates.success(title="Ping", description=t("cmd.ping.result", ping)))

	@commands.slash_command()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def about(self, ctx: discord.ApplicationContext) -> None:
		try:
			embed = discord.Embed(color=discord.Colour.blue())
			embed.set_author(name=App.NAME, icon_url=client.user.display_avatar.url)
			embed.set_footer(text=App.COPYRIGHT)
			embed.add_field(
				name="Version",
				value=f"`{App.VERSION_STRING}` (`{App.get_git_commit_hash()[0:7]}`)",
			)
			embed.add_field(
				name="Developer",
				value=f"- {App.DEVELOPER_NAME}\n\
  - [Website]({App.DEVELOPER_WEBSITE_URL})\n\
  - [Twitter]({App.DEVELOPER_TWITTER_URL})",
				inline=False,
			)
			await ctx.respond(embeds=[embed])
		except Exception:
			logger.error(traceback.format_exc())
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc()))
			)

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def sessions(self, ctx: discord.ApplicationContext) -> None:
		try:
			active_sessions = len(quiz_session_manager.sessions)
			max_sessions = int(getenv("MAX_SESSIONS", "0"))
			logger.info(getenv("MAX_SESSIONS"))

			limit_str = t("cmd.sessions.result.limit_none")
			if max_sessions > 0:
				limit_str = f"{max_sessions}"

			now = int(datetime.datetime.now().timestamp())

			embed = EmbedsTemplates.info(
				title=t("cmd.sessions.result.title"),
				description=f"{t('cmd.sessions.result.last_update')}: <t:{now}:f> (<t:{now}:R>)",
				icon="📊",
			)
			embed.add_field(name=t("cmd.sessions.result.current"), value=f"`{active_sessions}` / `{limit_str}`")
			await ctx.respond(embed=embed)
		except Exception:
			logger.error(traceback.format_exc())
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc()))
			)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(GeneralCommands(bot))
