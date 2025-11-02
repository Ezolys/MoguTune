import discord
from discord.ext import commands
from pycord.localizer import t

from introqbot.client import client
from introqbot.embeds import Notification


class GeneralCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def ping(self, ctx: discord.ApplicationContext) -> None:
		ping = round(client.latency * 1000)
		await ctx.respond(embed=Notification.success(title="Ping", description=t("cmd.ping.result", ping)))

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	async def test_embed(self, ctx: discord.ApplicationContext) -> None:
		await ctx.respond(
			embeds=[
				Notification.info(title="Test", description="Test1234"),
				Notification.success(description="Test1234"),
				Notification.warning(description="Test1234"),
				Notification.error(description="Test1234"),
				Notification.internal_error(description="Test1234"),
			]
		)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(GeneralCommands(bot))
