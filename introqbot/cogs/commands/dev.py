import logging
from os import getenv

import discord
from discord.ext import commands
from httpx import AsyncClient

from introqbot.chorus import YTMostReplayedAPI
from introqbot.embeds import EmbedsTemplates

logger = logging.getLogger(__name__)


class DevCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	@commands.is_owner()
	async def get_youtube_video_info(self, ctx: discord.ApplicationContext, url: str) -> None:
		await ctx.defer(ephemeral=True)

		# サビの情報を取得する
		chorus = await YTMostReplayedAPI.get_chorus_info(url)
		if not chorus:
			await ctx.followup.send(embed=EmbedsTemplates.error(description="Chorus data not found"), ephemeral=True)
			return

		chorus_sec = int(chorus / 1000)

		async with AsyncClient() as cl:
			res = await cl.get(
				YTMostReplayedAPI._API_URL + "videoinfo",
				params={"url": url},
				headers={"Secret": getenv("YTMRAPI_SECRET", "")},
				timeout=30,
			)
			if res.status_code == 200:
				d = res.json()
				if d.get("data") is not None:
					dt = d.get("data")
					# 埋め込みメッセージを生成
					emb = discord.Embed()
					emb.title = dt.get("title")
					emb.description = f"投稿日: <t:{dt.get('timestamp')}:f>\n再生時間: `{dt.get('duration_string')}`\n\n[▶️ **サビから再生**]({dt.get('original_url')}&t={chorus_sec}) ({chorus_sec} 秒)"
					emb.url = dt.get("original_url")
					# emb.timestamp = datetime.datetime.fromtimestamp(dt.get("timestamp"), tz=datetime.UTC)
					emb.set_author(name=dt.get("uploader"), url=dt.get("uploader_url"))
					emb.set_image(url=dt.get("thumbnail"))
					# 送信
					await ctx.followup.send(embed=emb, ephemeral=True)
				else:
					await ctx.followup.send(embed=EmbedsTemplates.error(description="Data not found"), ephemeral=True)
			else:
				await ctx.followup.send(
					embed=EmbedsTemplates.error(description=f"Request failed\n\nStatus code: {res.status_code}"), ephemeral=True
				)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(DevCommands(bot))
