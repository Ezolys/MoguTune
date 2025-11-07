import logging
import traceback

import discord
from discord.ext import commands
from pycord.localizer import t

from introqbot.app import App
from introqbot.client import client
from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates

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


def setup(bot: discord.Bot) -> None:
	bot.add_cog(GeneralCommands(bot))
