import discord
from client import tree
from discord.ext import commands


class IntroQ(commands.Cog):
	def init__(self, bot) -> None:
		self.bot = bot

	@tree.command(name="start", description="Start Introduction Quiz")
	async def start(self, ctx: discord.Interaction) -> None:
		await ctx.response.send_message("Introduction Quiz started", ephemeral=True)


async def setup(bot) -> None:
	await bot.add_cog(IntroQ(bot))
