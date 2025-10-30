from os import getenv

import discord
import discord.bot

from introqbot.localizations import Localization
from introqbot.logger import logger

intents = None
client = discord.bot.Bot(intents=intents)


# 接続完了時
@client.event
async def on_connect() -> None:
	logger.info("接続完了")
	# 言語データを読み込む
	Localization.load_locale_data()
	# Cogs の読み込み
	# await client.load_extension("cogs.commands")
	# await tree.sync(guild=discord.Object(id=1118692349250392184))


# 準備完了時
@client.event
async def on_ready() -> None:
	logger.info(f"ログイン完了: {client.user}")


def run() -> None:
	client.run(getenv("TOKEN", ""))
