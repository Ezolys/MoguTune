import logging
import traceback
from os import getenv

import discord
import mafic
from discord.ext import commands

from introqbot.debug_logger import DebugLogger
from introqbot.localizations import Localization
from introqbot.logger import setup_logging
from introqbot.quiz_session import quiz_session_manager

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


# 再生開始時イベント
@client.listen()
async def on_track_start(event: mafic.TrackEndEvent):
	assert isinstance(event.player, mafic.Player)
	guild_id = event.player.guild.id
	logger.debug(f"再生開始: {guild_id}")


# 再生終了時イベント
@client.listen()
async def on_track_end(event: mafic.TrackEndEvent):
	assert isinstance(event.player, mafic.Player)
	guild_id = event.player.guild.id
	logger.debug(f"再生終了: {guild_id}")
	session = quiz_session_manager.get_session(guild_id)
	if session is None:
		return
	# 次の問題へ進む
	session.NEXT.set()


# 接続完了時
# @client.event
# async def on_connect() -> None:
# 	logger.info("接続完了")
# 	# await client.load_extension("cogs.commands")
# 	# await client.tree.sync(guild=discord.Object(id=1118692349250392184))


# 準備完了時
@client.listen()
async def on_ready() -> None:
	# 内部エラー報告機能の初期化
	try:
		logger.info("デバッグ用サーバー/チャンネル取得")
		debug_gd_id = getenv("DEBUG_GUILD_ID", "")
		debug_ch_id = getenv("DEBUG_TEXT_CHANNEL_ID", "")
		DebugLogger.debug_guild = client.get_guild(int(debug_gd_id))
		DebugLogger.debug_channel = await DebugLogger.debug_guild.fetch_channel(debug_ch_id)
		if DebugLogger.debug_guild:
			logger.info("- サーバー: %s (ID: %d)", DebugLogger.debug_guild.name, DebugLogger.debug_guild.id)
		else:
			logger.warning("- サーバーが見つかりません: %s", debug_gd_id)
		if DebugLogger.debug_channel:
			logger.info("- チャンネル: %s (ID: %d)", DebugLogger.debug_channel.name, DebugLogger.debug_channel.id)
		else:
			logger.warning("- チャンネルが見つかりません: %s", debug_ch_id)
	except Exception:
		logger.error("内部エラー報告機能の初期化に失敗")
		logger.error(traceback.format_exc())

	logger.info(f"ログイン完了: {client.user}")


def run() -> None:
	# 言語データを読み込む
	i18n.load_locale_data()
	# Cogs の読み込み
	client.load_extensions("introqbot.cogs.commands")
	# コマンドのローカライズ
	i18n.localize_commands()
	# Bot の起動
	client.run(getenv("TOKEN", ""))
