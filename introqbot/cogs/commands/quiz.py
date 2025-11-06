import asyncio
import logging
import traceback

import discord
import mafic
from discord.ext import commands
from pycord.localizer import t

from introqbot.debug_logger import DebugLogger
from introqbot.embeds import EmbedsTemplates
from introqbot.quiz_session import quiz_session_manager

logger = logging.getLogger(__name__)


class QuizCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(send_messages=True)
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
			await asyncio.sleep(2)
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
					description=t("cmd.play.tracks_fetch_error"),
					error_code=await DebugLogger.report_internal_error(traceback.format_exc()),
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
		session = quiz_session_manager.create_session(ctx.guild.id, voice_channel.id, player)
		# VCに参加しているユーザーをプレイヤーとして追加する
		for u in voice_channel.voice_states:  # .members を使うと正しくメンバー一覧を取得できない
			# 自分自身とボットは除外
			if u == self.bot.user.id or (ctx.guild.get_member(u) or await ctx.guild.fetch_member(u)).bot:
				continue
			session.add_player(u)

		# クイズ準備完了メッセージ送信
		await msg.edit(
			embed=EmbedsTemplates.info(
				title=t("cmd.play.preparing_complete.title"), description=t("cmd.play.preparing_complete.description"), icon="☑️"
			)
		)
		# クイズ開始
		play_result = await session.play(tracks, q_count, ctx.user.id)

		# 内部エラー
		if isinstance(play_result, str):
			await msg.edit(embed=EmbedsTemplates.internal_error(error_code=play_result))

		# クイズセッションを削除する
		quiz_session_manager.delete_session(session.guild_id)

		# ボイスチャンネルから切断できていない場合は念の為切断する
		if voice_channel is not None and voice_channel.guild.voice_client is not None:
			await voice_channel.guild.voice_client.disconnect()

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def end(self, ctx: discord.ApplicationContext) -> None:
		if ctx.guild is None:
			logger.error("Guild is None")
			raise Exception("Guild is None")

		session = quiz_session_manager.get_session(ctx.guild.id)
		if session:
			# 実行者がクイズの主催者かチェック
			if session.owner is not None and session.owner.id != ctx.user.id:
				await ctx.respond(
					embed=EmbedsTemplates.error(
						description=t("cmd.end.do_not_have_permission"),
					),
					ephemeral=True,
				)
				return
			# クイズを強制終了する
			await quiz_session_manager.end_session(session.guild_id)
			await ctx.respond(
				embed=EmbedsTemplates.success(description=t("cmd.end.ended", ctx.guild.get_channel(session.channel_id).mention)),
				ephemeral=True,
			)
		else:
			await ctx.respond(embed=EmbedsTemplates.error(description=t("cmd.end.quiz_not_started")), ephemeral=True)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(QuizCommands(bot))
