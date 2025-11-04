import asyncio
import traceback

import discord
import mafic
from discord import SlashCommandGroup
from discord.ext import commands
from pycord.localizer import t

from introqbot.debug_logger import DebugLogger
from introqbot.embeds import Notification
from introqbot.quiz_session import QuizJoinView, quiz_session_manager


class QuizCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def start(self, ctx: discord.ApplicationContext, voice_channel: discord.VoiceChannel | None = None) -> None:
		if ctx.guild is None:
			return

		vc: discord.VoiceChannel | None = None

		# ボイスチャンネルが指定されていない場合はユーザーが接続しているボイスチャンネルにする
		if voice_channel is None:
			# ユーザーがボイスチャンネルに接続しているかチェック
			if ctx.user.voice is None:
				# ボイスチャンネルに参加していない場合はエラー
				await ctx.respond(embed=Notification.error(description=t("cmd.start.not_specified_voice_channel")))
				return
			if not isinstance(ctx.user.voice.channel, discord.VoiceChannel):
				# 参加しているチャンネルがボイスチャンネルではない場合はエラー
				await ctx.respond(embed=Notification.error(description=t("cmd.start.not_specified_voice_channel")))
				return
			vc = ctx.user.voice.channel
		else:
			vc = voice_channel

		# サーバー内で既にクイズが開始されているかチェック
		session = quiz_session_manager.get_session(ctx.guild.id)
		if session:
			await ctx.respond(
				embed=Notification.error(description=t("cmd.start.already_started", ctx.guild.get_channel(session.channel_id).mention))
			)
			return

		# クイズセッションを新規作成
		session = quiz_session_manager.create_session(vc.guild.id, vc.id)

		# クイズ作成通知を送信する
		await ctx.respond(
			embed=Notification.info(
				title=t("cmd.start.started.title"),
				description=t("cmd.start.started.description", ctx.guild.get_channel(session.channel_id).mention),
			),
			view=QuizJoinView(session_id=vc.guild.id),  # 参加ボタン
		)

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def end(self, ctx: discord.ApplicationContext) -> None:
		if ctx.guild is None:
			return

		session = quiz_session_manager.get_session(ctx.guild.id)

		if session:
			await session.end()
			quiz_session_manager.delete_session(session.guild_id)
			await ctx.respond(embed=Notification.success(description=t("cmd.end.ended", ctx.guild.get_channel(session.channel_id).mention)))
		else:
			await ctx.respond(embed=Notification.error(description=t("cmd.end.quiz_not_started")))

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
			return

		await ctx.defer()

		# msg = await ctx.send(embed=Notification.info(title=t("cmd.play.preparing.title"), description=t("cmd.q.preparing.loading")))

		session = quiz_session_manager.get_session(ctx.guild.id)
		if session is None:
			await ctx.send_followup(embed=Notification.error(description=t("cmd.play.quiz_not_started")))
			return
		vc: discord.VoiceChannel | None = ctx.guild.get_channel(session.channel_id)

		if vc is None:
			await ctx.send_followup(embed=Notification.error(description=t("cmd.start.quiz_not_started")))
			return

		# VCへ接続
		if vc.guild.voice_client:
			# 既に接続している場合は一度切断する
			await vc.guild.voice_client.disconnect()
		await asyncio.sleep(1)
		player = await vc.connect(cls=mafic.Player)

		# if not ctx.guild.voice_client:
		# 	player = await vc.connect(cls=mafic.Player)
		# else:
		# 	player = ctx.guild.voice_client

		search_type = mafic.SearchType.YOUTUBE

		try:
			tracks = await player.fetch_tracks(query, search_type)
		except Exception:
			ec = await DebugLogger.report_internal_error(traceback.format_exc())
			await ctx.send_followup(embed=Notification.internal_error(description=t("cmd.play.tracks_fetch_error"), error_code=ec))
			return

		# プレイリスト (楽曲) が見つからない場合は
		if not tracks:
			await ctx.send_followup(embed=Notification.error(description=t("cmd.play.no_tracks_found")))
			return
		# 指定されたクエリーがプレイリストではない場合
		if isinstance(tracks, list):
			await ctx.send_followup(embed=Notification.error(description=t("cmd.play.no_tracks_found")))
			return

		# クイズ開始
		await ctx.send_followup(
			embed=Notification.info(title=t("cmd.play.preparing_complete.title"), description=t("cmd.play.preparing_complete.description"))
		)
		await session.play(player, tracks, q_count)

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def quickplay(
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
			return

		await ctx.defer()

		# クイズセッションを開始
		await self.start(ctx)
		# クイズを開始
		await self.play(ctx, query, search_type, q_count)

	# @group.command()
	# @discord.guild_only()
	# @discord.default_permissions(administrator=True)
	# @commands.cooldown(2, 5)
	# async def stop(self, ctx: discord.ApplicationContext) -> None:
	# 	await ctx.defer()


def setup(bot: discord.Bot) -> None:
	bot.add_cog(QuizCommands(bot))
