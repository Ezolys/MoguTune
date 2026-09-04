import json
import logging
import sys
import traceback
from asyncio import sleep
from os import getenv

import discord
import sonolink
from discord.ext import commands, tasks
from mogutune_core.db import DBManager
from pycord.localizer import t
from sonolink.models import InactivitySettings

from mogutune.app import App
from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.kumasan import KumaSan
from mogutune.localizations import Localization
from mogutune.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class Bot(commands.Bot):
	def __init__(self, *args, **kwargs) -> None:
		super().__init__(*args, **kwargs)

		intents = discord.Intents.default()
		intents.voice_states = True

		# Lavalink (SonoLink)
		self.sl_client: sonolink.Client = sonolink.Client(self, framework="pycord")
		self.sl_started = False
		self._register_lavalink_node()

	def _register_lavalink_node(self) -> None:
		"""環境変数からLavalinkのノード情報を読み込んで登録する (接続は on_connect で行う)"""
		host = getenv("LAVALINK_HOST", "localhost")
		port = int(getenv("LAVALINK_PORT", "2333"))
		password = getenv("LAVALINK_PASSWORD", "youshallnotpass")
		secure = getenv("LAVALINK_SECURE", "false").lower() == "true"
		label = getenv("LAVALINK_LABEL", host)

		# sonolink 1.3.0 の create_node には secure 引数がないため、TLS は URI 形式で指定する
		# 自動切断 (Inactivity) は無効化し、切断管理はクイズセッション側に一任する
		if secure:
			self.sl_client.create_node(
				uri=f"https://{host}:{port}",
				password=password,
				id=label,
				inactivity_settings=InactivitySettings(timeout=None),
			)
		else:
			self.sl_client.create_node(
				host=host,
				port=port,
				password=password,
				id=label,
				inactivity_settings=InactivitySettings(timeout=None),
			)
		logger.info("Lavalink ノードを登録: %s:%d (Secure: %s, ID: %s)", host, port, secure, label)

	async def start_lavalink_nodes(self) -> None:
		"""登録済み Lavalink ノードへ接続する (on_connect から呼び出す)"""
		max_attempts = 5
		for attempt in range(1, max_attempts + 1):
			try:
				logger.info("Lavalink ノードへ接続 [試行 %d/%d]", attempt, max_attempts)
				await self.sl_client.start()
				self.sl_started = True
				break
			except Exception as e:
				logger.warning("Lavalink ノード接続失敗 [試行 %d/%d]: %s", attempt, max_attempts, e)
				if attempt < max_attempts:
					await sleep(5)
				else:
					logger.exception("Lavalink ノードへの接続に %d 回失敗しました", max_attempts)
					await KumaSan.ping(state="error", message=f"Lavalink ノードへの接続に {max_attempts} 回失敗しました")
					sys.exit(1)


intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
client = Bot(intents=intents)
if getenv("DEBUG", "false").lower() == "true":
	logger.info("デバッグモード有効")
	debug_guild_ids_raw = getenv("DEBUG_GUILD_ID", "")
	if debug_guild_ids_raw.strip():
		try:
			client.debug_guilds = [int(x.strip()) for x in debug_guild_ids_raw.split(",") if x.strip()]
			logger.info("デバッグギルドID: %s", client.debug_guilds)
		except ValueError:
			logger.warning("DEBUG_GUILD_ID の値が不正です: %s", debug_guild_ids_raw)
	else:
		logger.warning("DEBUG=true ですが DEBUG_GUILD_ID が未設定のため、グローバルコマンドとして登録されます")
i18n = Localization(client)


# 定期的に生存確認
@tasks.loop(minutes=1)
async def send_heartbeat() -> None:
	await KumaSan.ping()


# 1時間に1回プリセットを更新する
@tasks.loop(hours=1)
async def update_presets() -> None:
	await client.get_cog("QuizCommands").load_presets(i18n)


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
@client.event
async def on_application_command_error(
	ctx: discord.ApplicationContext,
	ex: discord.DiscordException,
) -> None:
	if i18n.i18n:
		await i18n.i18n.set_current_locale(ctx)

	full_command_name = ctx.command.qualified_name if ctx.command is not None else "!Unknown!"
	gn = None
	if ctx.guild is not None:
		gn = ctx.guild.name
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

	logger.error("アプリケーションコマンド実行エラー: %s", full_command_name)
	logger.error(ex)

	# クールダウン
	if isinstance(ex, commands.CommandOnCooldown):
		await ctx.respond(
			embed=EmbedsTemplates.warning(description=t("cmdmsg.cooldown_warning", int(ex.retry_after))),
			ephemeral=True,
		)
	# 実行者がオーナーではない
	elif isinstance(ex, commands.NotOwner):
		await ctx.respond(embed=EmbedsTemplates.error(description=t("cmdmsg.not_owner")), ephemeral=True)
	# その他
	else:
		# Pycord特有のラップされたエラーから元のエラーを取り出す
		original_ex = getattr(ex, "original", ex)

		# 例外オブジェクトから直接トレースバック文字列を生成する
		tb_strings = traceback.format_exception(type(original_ex), original_ex, original_ex.__traceback__)
		tb_text = "".join(tb_strings)

		# 内部エラーを報告してメッセージを送信する
		await ctx.respond(
			embed=EmbedsTemplates.internal_error(
				error_code=await DebugLogger.report_internal_error(
					"<Exception>\n" + str(original_ex) + "\n\n<Traceback>\n" + tb_text,
					description=(
						"<Application Command Error>\n"
						f"- {'DM' if gn is None else f'Guild: {gn} (`{ctx.guild_id}`)'}\n"
						f"- User: {ctx.user} (`{ctx.user.id}`)\n"
						f"- Command: `{full_command_name}`\n"
						"  - Options\n"
						+ (
							"\n".join(["    - `" + json.dumps(o) + "`" for o in ctx.selected_options])
							if ctx.selected_options
							else "    - None"
						)
					),
				),
			)
		)


# 接続確立時 (SonoLink のノード接続は on_ready ではなく on_connect で行う)
@client.listen()
async def on_connect() -> None:
	# 再接続時はスキップする
	if client.sl_started:
		return
	logger.info("接続完了")
	await client.start_lavalink_nodes()


# 準備完了時
@client.listen()
async def on_ready() -> None:
	# DBへ接続
	try:
		await DBManager.connect()
	except ConnectionError:
		sys.exit(1)

	# 内部エラー報告機能の初期化
	try:
		logger.info("デバッグ用サーバー/チャンネル取得")
		debug_gd_id = getenv("DEBUG_LOG_GUILD_ID", "")
		debug_ch_id = getenv("DEBUG_LOG_TEXT_CHANNEL_ID", "")
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

	# プリセットの定期更新開始
	update_presets.start()

	# 生存確認ループ開始
	if getenv("UPTIME_KUMA_PUSH_URL", "") != "":
		send_heartbeat.start()


def run() -> None:
	# 言語データを読み込む
	i18n.load_locale_data()
	# Cogs の読み込み
	client.load_extensions("mogutune.cogs.commands")
	# コマンドのローカライズ
	i18n.localize_commands()
	# コマンドグループのローカライズ
	i18n.localize_command_groups()
	# Bot の起動
	client.run(getenv("TOKEN", ""))
