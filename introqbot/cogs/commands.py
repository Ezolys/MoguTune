import discord
from discord.ext import commands


class QuizCommands(commands.Cog):
	def __init__(self, bot: commands.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def ping(self, ctx: commands.Context) -> None:
		await ctx.send("Pong...")
