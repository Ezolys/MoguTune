import logging

import discord
import mafic
from discord.ext import commands

from introqbot.localizations import Localization
from introqbot.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class Bot(commands.Bot):
	def __init__(self, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)

		intents = discord.Intents.default()
		intents.voice_states = True

		# Lavalink
		self.pool = mafic.NodePool(self)
		self.loop.create_task(self.add_nodes())

	async def add_nodes(self) -> None:
		# FIXME: 仮
		await self.pool.create_node(
			host="localhost",
			port=2333,
			label="localhost",
			password="youshallnotpass",
			secure=False,
		)


intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
client = Bot(intents=intents, debug_guilds=[1118692349250392184])
i18n = Localization(client)


def run() -> None:
	from os import getenv

	# 言語データを読み込む
	i18n.load_locale_data()
	# Cogs の読み込み
	client.load_extensions("introqbot.cogs.commands")
	client.load_extension("introqbot.events")
	# コマンドのローカライズ
	i18n.localize_commands()
	# Bot の起動
	client.run(getenv("TOKEN", ""))
