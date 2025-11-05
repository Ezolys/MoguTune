import logging
import traceback
from os import getenv

import discord
import mafic
from pycord.localizer import t

from introqbot.client import client
from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.quiz_session import quiz_session_manager

logger = logging.getLogger(__name__)


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

	# SEを読み込む
	node = client.pool.get_random_node()
	logger.info("効果音ファイル読み込み")
	for _key in quiz_session_manager.se:
		_p = getenv(_key)
		if _p is not None and _p != "":
			logger.info(f"- {_key}")
			_tr = await node.fetch_tracks(_p, search_type="http")
			if _tr is None:
				logger.warning(f" - 効果音が見つかりません: {_p}")
			else:
				logger.info(f" - 読み込み: {_p}")
			if isinstance(_tr, mafic.Track):
				quiz_session_manager.set_se(_key, _tr)
	# logger.info("効果音ファイル読み込み")
	# for _key in ("QUIZ_SE_CORRECT", "QUIZ_SE_INCORRECT", "QUIZ_SE_Q", "QUIZ_SE_A"):
	# 	_p = getenv(_key)
	# 	if _p is not None and _p != "":
	# 		_sp = ";".split(_p)
	# 		# 音量が指定されていない場合は
	# 		if len(_sp) == 1:
	# 			_p = _sp[0]
	# 			_vol = None
	# 		# 音量が指定されている場合は音量の値を渡す
	# 		else:
	# 			_p = "".join(_sp[0 : len(_sp) - 1])
	# 			_vol = _sp[len(_sp)]
	# 		_path = Path(_p)
	# 		if _path.exists():
	# 			logger.info(f"- {_key}: {_p}")
	# 			quiz_session_manager.set_se(_key, _p, _vol)
	# 		else:
	# 			logger.warning(f"- ファイルが見つかりません - {_key}: {_p}")

	logger.info(f"ログイン完了: {client.user}")


# ボイスチャンネルステータス変更時 (参加/退出等) イベント
@client.listen()
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
	session = quiz_session_manager.get_session(member.guild.id)
	# 対象のサーバーでクイズが行われている場合はメンバーのチェックを実行する
	if session is None:
		return

	# クイズが行われているボイスチャンネルに参加した
	if after.channel is not None and after.channel.id == session.channel_id:
		# 自分自身とボットは除外
		if member.id == client.user.id or member.bot:
			return
		# 参加待ちの列へ追加する
		session.add_queue(member.id)
	# クイズが行われているボイスチャンネルから退出した
	elif before.channel is not None and after.channel is None and before.channel.id == session.channel_id:
		# プレイヤーから削除する
		session.remove_player(member.id)
		session.remove_queue(member.id)


# 再生開始時イベント
@client.listen()
async def on_track_start(event: mafic.TrackStartEvent) -> None:
	logger.info("再生開始: %s - %s", event.player.guild.id, event.track.title)
	session = quiz_session_manager.get_session(event.player.guild.id)
	if session:
		# 再生されたトラックがSEではない場合のみ current_track を更新する
		if event.track not in quiz_session_manager.se.values():
			logger.info("- 再生中トラック更新")
			session.current_track = event.track


# 再生終了時イベント
@client.listen()
async def on_track_end(event: mafic.TrackEndEvent) -> None:
	logger.info("再生終了: %s - %s", event.player.guild.id, event.track.title)
	session = quiz_session_manager.get_session(event.player.guild.id)
	if session:
		if session.se_playing:
			session.se_playing = False
			session.SE_PLAYING_EVENT.set()
		else:
			logger.info("- 再生中トラック削除")
			session.current_track = None
			# 次の問題へ
			if session.playing:
				session.NEXT.set()
