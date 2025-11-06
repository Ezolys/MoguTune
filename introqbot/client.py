import logging
import traceback
from os import getenv

import discord
import mafic
from discord.ext import commands, tasks
from pycord.localizer import t

from introqbot.app import App
from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.kumasan import KumaSan
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
		"""環境変数からLavalinkのノード情報を読み込んで追加する"""
		host = getenv("LAVALINK_HOST", "localhost")
		port = int(getenv("LAVALINK_PORT", "2333"))
		password = getenv("LAVALINK_PASSWORD", "youshallnotpass")
		secure = getenv("LAVALINK_SECURE", "false").lower() == "true"
		label = getenv("LAVALINK_LABEL", host)

		logger.info("Lavalink ノードを追加: %s:%d (Secure: %s)", host, port, secure)
		await self.pool.create_node(
			host=host,
			port=port,
			label=label,
			password=password,
			secure=secure,
		)


intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
client = Bot(intents=intents, debug_guilds=[1118692349250392184, 1378181427945930843])
i18n = Localization(client)


# 定期的に生存確認
@tasks.loop(minutes=1)
async def send_heartbeat() -> None:
	await KumaSan.ping()


# アプリケーションコマンド実行時のイベント
@client.listen()
async def on_application_command_completion(ctx: discord.ApplicationContext) -> None:
	if ctx.command is None:
		logger.warning("アプリケーションコマンド実行 - コマンドが見つかりません: %s", ctx.command)
		return

	full_command_name = ctx.command.qualified_name
	if ctx.guild is not None:
		logger.info(
			"アプリケーションコマンド実行 - %s | ギルド: %s (%d) | 実行者: %s (%s)",
			full_command_name,
			ctx.guild.name,
			ctx.guild.id,
			ctx.user,
			ctx.user.id,
		)
	else:
		logger.info(
			"アプリケーションコマンド実行 - %s | DM | 実行者: %s (%s)",
			full_command_name,
			ctx.user,
			ctx.user.id,
		)


# アプリケーションコマンドエラー時のイベント
@client.listen()
async def on_application_command_error(
	ctx: discord.ApplicationContext,
	ex: discord.DiscordException,
) -> None:
	cmd_name = "!Unknown!"
	if ctx.command is not None:
		cmd_name = ctx.command.qualified_name

	logger.error("アプリケーションコマンド実行エラー: %s", cmd_name)
	logger.error(ex)

	# クールダウン
	if str(ex).startswith("You are on cooldown"):
		await ctx.respond(
			embed=EmbedsTemplates.warning(description=t("cmdmsg.cooldown_warning")),
			ephemeral=True,
		)
	# その他
	else:
		# 内部エラーを報告してメッセージを送信する
		await ctx.respond(
			embed=EmbedsTemplates.internal_error(
				error_code=await DebugLogger.report_internal_error("Exception: " + str(ex) + "\n\n" + traceback.format_exc())
			)
		)


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

	# ステータス表示を更新
	await client.change_presence(
		activity=discord.Game(name=f"/play | v{App.VERSION_STRING}"),
	)

	await KumaSan.ping(message=f"ログイン完了 ({client.latency * 1000} ms)")

	logger.info(f"ログイン完了: {client.user} ({client.latency * 1000} ms)")

	# 生存確認ループ開始
	send_heartbeat.start()


def run() -> None:
	# 言語データを読み込む
	i18n.load_locale_data()
	# Cogs の読み込み
	client.load_extensions("introqbot.cogs.commands")
	# コマンドのローカライズ
	i18n.localize_commands()
	# Bot の起動
	client.run(getenv("TOKEN", ""))
