import asyncio
import logging
import traceback
from os import getenv

import discord
import mafic
from pycord.localizer import t

from mogutune.client import client
from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.quiz.manager import quiz_session_manager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


async def prepare_play(
	inter: discord.Interaction,
	user: discord.Member,
	guild: discord.Guild,
	query: str = "",
	q_count: int = 10,
) -> None:
	"""クイズを開始する"""
	session = None
	try:
		# プレイリストのURLとプリセットどちらも指定されていない場合はエラーメッセージを返す
		if query == "":
			await inter.respond(embed=EmbedsTemplates.error(description=t("cmd.play.no_query")), ephemeral=True)
			return

		if isinstance(inter, discord.Message):
			msg = inter
		else:
			# 準備中メッセージを送信
			_inter = await inter.response.send_message(
				embed=EmbedsTemplates.info(title=t("cmd.play.preparing.title"), description=t("cmd.play.preparing.description"), icon="🔳"),
				ephemeral=True,
			)
			msg = await _inter.original_message()

		if msg is None:
			return

		# ユーザーがボイスチャンネルに接続しているかチェック
		if user.voice is None:
			# ボイスチャンネルに参加していない場合はエラー
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.start.not_specified_voice_channel")))
			return
		if not isinstance(user.voice.channel, discord.VoiceChannel):
			# 参加しているチャンネルがボイスチャンネルではない場合はエラー
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.start.not_specified_voice_channel")))
			return

		voice_channel: discord.VoiceChannel = user.voice.channel

		# サーバー内で既にクイズが開始されているかチェック
		session = quiz_session_manager.get_session(guild.id)
		if session:
			await msg.edit(
				embed=EmbedsTemplates.error(description=t("cmd.start.already_started", guild.get_channel(session.channel_id).mention))
			)
			return

		# セッション数制限チェック
		max_sessions = int(getenv("MAX_SESSIONS", "0"))
		if max_sessions > 0 and len(quiz_session_manager.sessions) >= max_sessions:
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.start.limit_reached")))
			return

		# VCへ接続
		if voice_channel.guild.voice_client is not None:
			# 既に接続している場合は一度切断する
			await voice_channel.guild.voice_client.disconnect()
			await asyncio.sleep(2)

		try:
			player = await voice_channel.connect(cls=mafic.Player)
		except Exception:
			await msg.edit(embed=EmbedsTemplates.error(description=t("cmd.play.cannot_connect_voice_channel")))
			return

		# 検索タイプ
		search_type = mafic.SearchType.YOUTUBE_MUSIC
		# search_type = mafic.SearchType[search_type]

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
		session = quiz_session_manager.create_session(guild.id, voice_channel.id, player, query)
		bot_id = client.user.id if client.user else 0
		# VCに参加しているユーザーをプレイヤーとして追加する
		for u in voice_channel.voice_states:  # .members を使うと正しくメンバー一覧を取得できない
			# 自分自身は除外
			_m = await guild.get_or_fetch(discord.Member, u)
			if u == bot_id:
				continue
			# ボットは除外
			if _m is not None and _m.bot:
				continue
			# クイズにユーザーを追加
			await session.add_player(u)

		# クイズ準備完了メッセージ送信
		await msg.edit(
			embed=EmbedsTemplates.info(
				title=t("cmd.play.preparing_complete.title"),
				description=t("cmd.play.preparing_complete.description", voice_channel.mention),
				icon="☑️",
			)
		)
		# クイズ開始
		play_result = await session.play(tracks, q_count, user.id, query)

		# 内部エラー
		if isinstance(play_result, str):
			await msg.edit(embed=EmbedsTemplates.internal_error(error_code=play_result))

		# クイズセッションを終了する
		await quiz_session_manager.end_session(session.guild_id)

		# ボイスチャンネルから切断できていない場合は念の為切断する
		if voice_channel is not None and voice_channel.guild.voice_client is not None:
			await voice_channel.guild.voice_client.disconnect()

	except Exception:
		try:
			# クイズセッションを終了する
			if session is not None:
				await quiz_session_manager.end_session(session.guild_id)
		except Exception:
			logger.error("クイズ実行エラー - クイズ終了失敗")
			logger.error(traceback.format_exc())
		err_code = await DebugLogger.report_internal_error("クイズ実行エラー\n\n" + traceback.format_exc())
		try:
			if inter.channel is not None and not isinstance(
				inter.channel, (discord.CategoryChannel, discord.ForumChannel, discord.MediaChannel)
			):
				await inter.channel.send(embed=EmbedsTemplates.internal_error(error_code=err_code))
		except Exception:
			logger.exception("Internal Error Message Send Failed")
