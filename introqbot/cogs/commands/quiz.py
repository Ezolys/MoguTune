import asyncio
import logging
import traceback

import discord
import mafic
from discord import SlashCommandGroup
from discord.ext import commands
from pycord.localizer import t

from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.quiz_session import QuizJoinView, quiz_session_manager

logger = logging.getLogger(__name__)


class QuizCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def play(
		self,
		ctx: discord.ApplicationContext,
		query: str,
		search_type: discord.Option(
			input_type=str,
			required=False,
			default=mafic.SearchType.YOUTUBE.name,
			choices=[
				discord.OptionChoice("Spotify", mafic.SearchType.SPOTIFY_SEARCH.name),
				discord.OptionChoice("YouTube", mafic.SearchType.YOUTUBE.name),
			],
		),  # pyright: ignore[reportInvalidTypeForm]
		q_count: discord.Option(int, min_value=1, max_value=50, required=False, default=10),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		if ctx.guild is None:
			logger.error("Guild is None")
			raise Exception("Guild is None")

		# 準備中メッセージを送信
		msg = await ctx.respond(
			embed=EmbedsTemplates.info(title=t("cmd.play.preparing.title"), description=t("cmd.play.preparing.description"), icon="🔳"),
			ephemeral=True,
		)

		# ユーザーがボイスチャンネルに接続しているかチェック
		if ctx.user.voice is None:
			# ボイスチャンネルに参加していない場合はエラー
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.start.not_specified_voice_channel")))
			return
		if not isinstance(ctx.user.voice.channel, discord.VoiceChannel):
			# 参加しているチャンネルがボイスチャンネルではない場合はエラー
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.start.not_specified_voice_channel")))
			return

		voice_channel: discord.VoiceChannel = ctx.user.voice.channel

		# サーバー内で既にクイズが開始されているかチェック
		session = quiz_session_manager.get_session(ctx.guild.id)
		if session:
			await msg.edit(
				embed=EmbedsTemplates.error(description=t("cmd.start.already_started", ctx.guild.get_channel(session.channel_id).mention))
			)
			return

		# VCへ接続
		if voice_channel.guild.voice_client:
			# 既に接続している場合は一度切断する
			await voice_channel.guild.voice_client.disconnect()
			await asyncio.sleep(1)
		player = await voice_channel.connect(cls=mafic.Player)

		# 検索タイプ
		search_type = mafic.SearchType[search_type]

		# プレイリストを検索
		logger.debug(f"プレイリスト検索 - {search_type}: {query}")
		try:
			tracks = await player.fetch_tracks(query, search_type)
		except Exception:
			if voice_channel.guild.voice_client:
				# 切断する
				await voice_channel.guild.voice_client.disconnect()
			await msg.edit(
				embed=EmbedsTemplates.internal_error(
					description=t("cmd.play.tracks_fetch_error"), error_code=await DebugLogger.report_internal_error(traceback.format_exc())
				)
			)
			return

		# プレイリスト (楽曲) が見つからない場合
		if not tracks:
			if voice_channel.guild.voice_client:
				# 切断する
				await voice_channel.guild.voice_client.disconnect()
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.play.no_tracks_found")))
			return
		# 指定されたクエリーがプレイリストではない場合
		if isinstance(tracks, list):
			if voice_channel.guild.voice_client:
				# 切断する
				await voice_channel.guild.voice_client.disconnect()
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.play.not_a_playlist_url")))
			return

		# クイズセッションを新規作成
		session = quiz_session_manager.create_session(voice_channel.guild.id, voice_channel.id, player)
		# VCに参加しているユーザーをプレイヤーとして追加する
		for u in voice_channel.members:
			# 自分自身とボットは除外
			if u.id == self.bot.user.id or u.bot:
				continue
			session.add_player(u.id)

		# クイズ開始
		await msg.edit(
			embed=EmbedsTemplates.info(
				title=t("cmd.play.preparing_complete.title"), description=t("cmd.play.preparing_complete.description"), icon="☑️"
			)
		)
		await session.play(tracks, q_count)

		# ボイスチャンネルから切断する
		await voice_channel.guild.voice_client.disconnect()

		# クイズセッションを削除する
		quiz_session_manager.delete_session(session.guild_id)

	# @group.command()
	# @discord.guild_only()
	# @discord.default_permissions(administrator=True)
	# @commands.cooldown(2, 5)
	# async def stop(self, ctx: discord.ApplicationContext) -> None:
	# 	await ctx.defer()


def setup(bot: discord.Bot) -> None:
	bot.add_cog(QuizCommands(bot))
