import discord
from discord.ext import commands
from pycord.localizer import t

from introqbot.client import client
from introqbot.embeds import Notification


class QuizCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def ping(self, ctx: discord.ApplicationContext) -> None:
		ping = round(client.latency * 1000)
		await ctx.respond(embed=Notification.success(title="Ping", description=t("cmd.ping.result", ping)))


def setup(bot: discord.Bot) -> None:
	bot.add_cog(QuizCommands(bot))
