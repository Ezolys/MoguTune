import datetime
import json
import logging
import math
import os
import sys
import traceback
from asyncio import sleep, wait_for
from os import getenv

import discord
import sonolink
from discord.ext import commands, tasks
from mogutune_core.db import DBManager
from pycord.localizer import t
from sonolink.models import InactivitySettings

from mogutune import telemetry
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

		# ダッシュボード表示用の起動時刻
		self.started_at = datetime.datetime.now(tz=datetime.UTC)

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
		# retries 未指定だと node.connect() が無限リトライして on_connect をブロックするため有限回にする
		if secure:
			self.sl_client.create_node(
				uri=f"https://{host}:{port}",
				password=password,
				id=label,
				retries=3,
				inactivity_settings=InactivitySettings(timeout=None),
			)
		else:
			self.sl_client.create_node(
				host=host,
				port=port,
				password=password,
				id=label,
				retries=3,
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
				# sonolink の start() は接続失敗を例外で通知しない (内部で握りつぶす) ため、接続結果を直接検証する
				if not any(n.is_connected for n in self.sl_client.nodes):
					raise RuntimeError("Lavalink ノードが接続されていません")
				self.sl_started = True
				connected = [n.id for n in self.sl_client.nodes if n.is_connected]
				logger.info("Lavalink ノードへ接続しました: %s", ", ".join(connected))
				break
			except Exception as e:
				logger.warning("Lavalink ノード接続失敗 [試行 %d/%d]: %s", attempt, max_attempts, e)
				if attempt < max_attempts:
					await sleep(5)
				else:
					logger.exception("Lavalink ノードへの接続に %d 回失敗しました", max_attempts)
					await KumaSan.ping(state="error", message=f"Lavalink ノードへの接続に {max_attempts} 回失敗しました")
					# イベントタスク内では sys.exit がプロセスを終了させないため os._exit で確実に終了する
					os._exit(1)


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

# ダッシュボード向けテレメトリの設定
BOT_STATUS_INTERVAL_SECONDS = 30
"""稼働状況をダッシュボードへ記録する間隔 (秒)"""
GUILD_SYNC_INTERVAL_MINUTES = 10
"""サーバー一覧を再同期する間隔 (分)"""


def _guild_info(guild: discord.Guild) -> telemetry.GuildInfo:
	"""discord.Guild からテレメトリ用のサーバー情報を生成する"""
	# pycord の Guild には joined_at が無いため、Bot 自身の Member から取得する (取得できない場合は None)
	me = guild.me
	return telemetry.GuildInfo(
		id=guild.id,
		name=guild.name,
		member_count=guild.member_count or 0,
		icon_url=guild.icon.url if guild.icon is not None else None,
		joined_at=me.joined_at if me is not None else None,
	)


def _build_bot_status() -> dict:
	"""ダッシュボードへ記録する稼働状況のスナップショットを生成する"""
	from mogutune.quiz import quiz_session_manager  # noqa: PLC0415

	sessions: list[dict] = []
	for session in quiz_session_manager.sessions.values():
		try:
			sessions.append(session.status_snapshot())
		except Exception:
			logger.exception("クイズセッションの状態取得に失敗")

	nodes: list[dict] = []
	try:
		for node in client.sl_client.nodes:
			stats = node.stats
			nodes.append(
				{
					"id": node.id,
					"connected": node.is_connected,
					"connecting": node.is_connecting,
					"players": getattr(stats, "players", None),
					"playing_players": getattr(stats, "playing_players", None),
				}
			)
	except Exception:
		logger.exception("Lavalink ノードの状態取得に失敗")

	return {
		"version": App.VERSION_STRING,
		"commit": App.get_git_commit_hash()[:7],
		# 未接続時は latency が NaN になるため 0 として扱う
		"latency_ms": 0 if math.isnan(client.latency) else round(client.latency * 1000),
		"guild_count": len(client.guilds),
		"user_count": sum(guild.member_count or 0 for guild in client.guilds),
		"active_sessions": sessions,
		"lavalink": nodes,
		"started_at": client.started_at,
	}


@tasks.loop(seconds=BOT_STATUS_INTERVAL_SECONDS)
async def report_bot_status() -> None:
	"""稼働状況を定期的にダッシュボード向けへ記録する"""
	await telemetry.update_bot_status(_build_bot_status())


@tasks.loop(minutes=GUILD_SYNC_INTERVAL_MINUTES)
async def refresh_guilds() -> None:
	"""サーバー一覧 (人数など) を定期的に再同期する"""
	await telemetry.sync_guilds([_guild_info(guild) for guild in client.guilds])


# 定期的に生存確認
@tasks.loop(minutes=1)
async def send_heartbeat() -> None:
	await KumaSan.ping()


# 1時間に1回プリセットを更新する
@tasks.loop(hours=1)
async def update_presets() -> None:
	await client.get_cog("QuizCommands").load_presets(i18n)


# Lavalink ノード監視の設定
LAVALINK_CHECK_INTERVAL_MINUTES = 5
LAVALINK_HEALTHCHECK_TIMEOUT_S = 10.0


# 5分に1回 Lavalink ノードの接続を確認し、未接続・応答不能なら再接続を試みる (起動時失敗は終了済みのため警告に留める)
@tasks.loop(minutes=LAVALINK_CHECK_INTERVAL_MINUTES)
async def check_lavalink_nodes() -> None:
	if not client.sl_started:
		return
	try:
		nodes = list(client.sl_client.nodes)
	except Exception:
		logger.exception("Lavalink ノード一覧の取得に失敗")
		return
	if not nodes:
		# ノード登録自体がない状態は通常発生しない (start() も対象がないため再接続できない)
		logger.warning("Lavalink ノードが登録されていません")
		return

	for node in nodes:
		# 接続処理中のノードは sonolink 側の自動再接続に任せる
		if node.is_connecting:
			continue

		if not node.is_connected:
			# sonolink の自動再接続が retries を使い切った後は connect() が無視されるため reconnect() を使う
			logger.warning("Lavalink ノード %s が未接続のため再接続を試みます", node.id)
		else:
			# 接続中でも REST が応答しない場合はゾンビ接続とみなす
			try:
				await wait_for(node.fetch_info(), timeout=LAVALINK_HEALTHCHECK_TIMEOUT_S)
			except Exception as e:
				logger.warning("Lavalink ノード %s が応答しないため再接続を試みます: %s", node.id, e)
			else:
				continue

		try:
			await node.reconnect()
		except RuntimeError as e:
			# すでに sonolink 側で再接続が始まっていた場合など
			logger.warning("Lavalink ノード %s の再接続をスキップ: %s", node.id, e)
		except Exception:
			logger.exception("Lavalink ノード %s の再接続に失敗", node.id)


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

	# ダッシュボード向けにコマンド実行ログを記録する
	await telemetry.record_command(
		telemetry.CommandRecord(
			command=full_command_name,
			guild_id=ctx.guild_id,
			guild_name=ctx.guild.name if ctx.guild is not None else None,
			channel_id=ctx.channel_id,
			user_id=ctx.user.id,
			options=[json.dumps(option, ensure_ascii=False) for option in ctx.selected_options or []],
		)
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

	def build_record(error_type: str, error_code: str | None = None) -> telemetry.CommandRecord:
		"""失敗したコマンドの記録を生成する"""
		return telemetry.CommandRecord(
			command=full_command_name,
			ok=False,
			guild_id=ctx.guild_id,
			guild_name=gn,
			channel_id=ctx.channel_id,
			user_id=ctx.user.id,
			options=[json.dumps(option, ensure_ascii=False) for option in ctx.selected_options or []],
			error_type=error_type,
			error_code=error_code,
		)

	# クールダウン
	if isinstance(ex, commands.CommandOnCooldown):
		await telemetry.record_command(build_record("cooldown"))
		await ctx.respond(
			embed=EmbedsTemplates.warning(description=t("cmdmsg.cooldown_warning", int(ex.retry_after))),
			ephemeral=True,
		)
	# 実行者がオーナーではない
	elif isinstance(ex, commands.NotOwner):
		await telemetry.record_command(build_record("not_owner"))
		await ctx.respond(embed=EmbedsTemplates.error(description=t("cmdmsg.not_owner")), ephemeral=True)
	# その他
	else:
		# Pycord特有のラップされたエラーから元のエラーを取り出す
		original_ex = getattr(ex, "original", ex)

		# 例外オブジェクトから直接トレースバック文字列を生成する
		tb_strings = traceback.format_exception(type(original_ex), original_ex, original_ex.__traceback__)
		tb_text = "".join(tb_strings)

		# 内部エラーを報告してメッセージを送信する
		error_code = await DebugLogger.report_internal_error(
			"<Exception>\n" + str(original_ex) + "\n\n<Traceback>\n" + tb_text,
			description=(
				"<Application Command Error>\n"
				f"- {'DM' if gn is None else f'Guild: {gn} (`{ctx.guild_id}`)'}\n"
				f"- User: {ctx.user} (`{ctx.user.id}`)\n"
				f"- Command: `{full_command_name}`\n"
				"  - Options\n"
				+ ("\n".join(["    - `" + json.dumps(o) + "`" for o in ctx.selected_options]) if ctx.selected_options else "    - None")
			),
			source=full_command_name,
			guild_id=ctx.guild_id,
			user_id=ctx.user.id,
			command=full_command_name,
		)
		await telemetry.record_command(build_record("internal", error_code))
		await ctx.respond(embed=EmbedsTemplates.internal_error(error_code=error_code))


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

	# ダッシュボード向けテレメトリの初期化 (失敗しても on_ready の残りを止めない)
	try:
		await telemetry.ensure_indexes()
		await telemetry.sync_guilds([_guild_info(guild) for guild in client.guilds])
	except Exception:
		logger.exception("テレメトリの初期化に失敗")

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

	# Lavalink 接続監視ループ開始
	check_lavalink_nodes.start()

	# ダッシュボード向けの稼働状況記録・サーバー一覧同期を開始
	if not report_bot_status.is_running():
		report_bot_status.start()
	if not refresh_guilds.is_running():
		refresh_guilds.start()


# サーバー参加時
@client.listen()
async def on_guild_join(guild: discord.Guild) -> None:
	await telemetry.upsert_guild(_guild_info(guild))


# サーバー退出時
@client.listen()
async def on_guild_remove(guild: discord.Guild) -> None:
	await telemetry.remove_guild(guild.id)


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
