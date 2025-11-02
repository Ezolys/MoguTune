import logging
from os import getenv

import discord

from introqbot.localizations import Localization
from introqbot.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.voice_states = True
client = discord.Bot(intents=intents, debug_guilds=[1118692349250392184])
i18n = Localization(client)


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
	i18n.load_locale_data()
	# Cogs の読み込み
	# client.load_extensions("introqbot.cogs")
	# client.load_cogs("./introqbot/cogs")
	# コマンドのローカライズ
	i18n.localize_commands()
	# Bot の起動
	client.run(getenv("TOKEN", ""))
