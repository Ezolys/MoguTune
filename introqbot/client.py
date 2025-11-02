from os import getenv

import discord

from introqbot.localizations import Localization
from introqbot.logger import logger

intents = discord.Intents.default()
intents.voice_states = True
client = discord.Bot(intents=intents, debug_guilds=[1118692349250392184])


# 接続完了時
# @client.event
# async def on_connect() -> None:
# 	logger.info("接続完了")
# 	# await client.load_extension("cogs.commands")
# 	# await client.tree.sync(guild=discord.Object(id=1118692349250392184))


# 準備完了時
@client.event
async def on_ready() -> None:
	logger.info(f"ログイン完了: {client.user}")


def run() -> None:
	# 言語データを読み込む
	Localization.load_locale_data()
	# Cogs の読み込み
	# client.load_cogs("./introqbot/cogs")
	# コマンドのローカライズ
	# Localization.localize_commands(client)
	# Bot の起動
	client.run(getenv("TOKEN", ""))
