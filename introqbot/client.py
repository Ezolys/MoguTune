from os import getenv

import discord
from discord import Intents
from discord.ext import commands

from introqbot.localizations import Localization
from introqbot.logger import logger

intents = Intents.default()
client = commands.Bot(command_prefix="iq:", intents=intents)
tree = client.tree


# 接続完了時
@client.event
async def on_connect() -> None:
	logger.info("接続完了")
	# 言語データを読み込む
	Localization.load_locale_data()
	# Cogs の読み込み
	await client.load_extension("cogs.commands")
	await tree.sync(guild=discord.Object(id=1118692349250392184))


# 準備完了時
@client.event
async def on_ready() -> None:
	logger.info(f"ログイン完了: {client.user}")


def run() -> None:
	client.run(getenv("TOKEN", ""))
