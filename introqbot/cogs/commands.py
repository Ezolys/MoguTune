import discord
from discord.ext import commands

from introqbot.client import client
from introqbot.embeds import Notification


class QuizCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@client.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def ping(self, ctx: discord.ApplicationContext) -> None:
		ping = round(client.latency * 1000)
		await ctx.respond(Notification.success(title="Ping", description=f"`{ping}` ms"))


def setup(bot: discord.Bot) -> None:
	bot.add_cog(QuizCommands(bot))
