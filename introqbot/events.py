import logging
import traceback
from os import getenv

import discord
import mafic
from discord.ext import commands
from pycord.localizer import t

from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.quiz_session import quiz_session_manager

logger = logging.getLogger(__name__)


class EventListeners(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	# アプリケーションコマンド実行時のイベント
	@commands.Cog.listener()
	async def on_application_command_completion(self, ctx: discord.ApplicationContext) -> None:
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
	@commands.Cog.listener()
	async def on_application_command_error(
		self,
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

	# 準備完了時
	@commands.Cog.listener()
	async def on_ready(self) -> None:
		# 内部エラー報告機能の初期化
		try:
			logger.info("デバッグ用サーバー/チャンネル取得")
			debug_gd_id = getenv("DEBUG_GUILD_ID", "")
			debug_ch_id = getenv("DEBUG_TEXT_CHANNEL_ID", "")
			DebugLogger.debug_guild = self.bot.get_guild(int(debug_gd_id))
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

		logger.info(f"ログイン完了: {self.bot.user}")

	# ボイスチャンネルステータス変更時 (参加/退出等) イベント
	@commands.Cog.listener()
	async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
		session = quiz_session_manager.get_session(member.guild.id)
		# 対象のサーバーでクイズが行われている場合はメンバーのチェックを実行する
		if session is None:
			return

		# クイズが行われているボイスチャンネルに参加した
		if after.channel is not None and after.channel.id == session.channel_id:
			# 自分自身とボットは除外
			if member.id == self.bot.user.id or member.bot:
				return
			# 参加待ちの列へ追加する
			session.add_queue(member.id)
		# クイズが行われているボイスチャンネルから退出した
		elif before.channel is not None and after.channel is None and before.channel.id == session.channel_id:
			# プレイヤーから削除する
			session.remove_player(member.id)
			session.remove_queue(member.id)

	# 再生開始時イベント
	@commands.Cog.listener()
	async def on_track_start(self, event: mafic.TrackStartEvent) -> None:
		assert isinstance(event.player, mafic.Player)
		guild_id = event.player.guild.id
		logger.debug(f"再生開始イベント: {guild_id}")

	# 再生終了時イベント
	@commands.Cog.listener()
	async def on_track_end(self, event: mafic.TrackEndEvent) -> None:
		assert isinstance(event.player, mafic.Player)
		guild_id = event.player.guild.id
		session = quiz_session_manager.get_session(guild_id)
		if session is None:
			return

		logger.debug(f"再生終了イベント: {guild_id} - {event.reason} - SFX再生中: {session.is_playing_sfx}")

		# 効果音の再生が終了した場合
		if session.is_playing_sfx and session.sfx_player:
			if event.reason == mafic.TrackEndReason.FINISHED:
				session.sfx_player.sfx_finished.set()
			return

		# クイズの曲が終了した場合
		if not session.is_playing_sfx:
			session.NEXT.set()


def setup(bot: discord.Bot) -> None:
	bot.add_cog(EventListeners(bot))
