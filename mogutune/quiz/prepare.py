import asyncio
import logging
import traceback
from os import getenv

import discord
import sonolink
from mogutune_core.db import DBManager
from pycord.localizer import t
from sonolink.models import Playable as SonoPlayable
from sonolink.models import Playlist as SonoPlaylist

from mogutune.client import client
from mogutune.debug_logger import DebugLogger
from mogutune.discord_io import safe_edit, safe_send
from mogutune.embeds import EmbedsTemplates
from mogutune.playlists import Playlist
from mogutune.quiz.manager import quiz_session_manager
from mogutune.quiz.permissions import check_voice_permissions
from mogutune.quiz.track_adapter import TrackCollection, unpack_search

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


async def _leave_vc(guild: discord.Guild) -> bool:
	"""VCに残留接続があれば切断する (失敗時はログのみ残す)。切断したら True を返す"""
	try:
		voice_client = guild.voice_client
		if voice_client is None:
			return False
		await voice_client.disconnect()
	except Exception:
		logger.exception("残留VC接続の切断に失敗")
		return False
	return True


async def prepare_play(  # noqa: C901, PLR0911, PLR0912, PLR0915
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
			await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.start.not_specified_voice_channel")))
			return
		if not isinstance(user.voice.channel, discord.VoiceChannel):
			# 参加しているチャンネルがボイスチャンネルではない場合はエラー
			await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.start.not_specified_voice_channel")))
			return

		voice_channel: discord.VoiceChannel = user.voice.channel

		# 実行元テキストチャンネルID（フォールバック通知先）
		text_channel_id: int | None = None
		try:
			_ch = getattr(inter, "channel", None)
			if (
				_ch is not None
				and not isinstance(_ch, (discord.CategoryChannel, discord.ForumChannel, discord.MediaChannel))
				and hasattr(_ch, "id")
			):
				text_channel_id = _ch.id  # type: ignore[attr-defined]
		except Exception:
			text_channel_id = None

		# サーバー内で既にクイズが開始されているかチェック
		session = quiz_session_manager.get_session(guild.id)
		if session:
			await safe_edit(
				msg,
				embed=EmbedsTemplates.error(description=t("cmd.start.already_started", guild.get_channel(session.channel_id).mention)),
			)
			return

		# セッション数制限チェック
		max_sessions = int(getenv("MAX_SESSIONS", "0"))
		if max_sessions > 0 and len(quiz_session_manager.sessions) >= max_sessions:
			await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.start.limit_reached")))
			return

		# 事前権限チェック（不足があれば詳細メッセージで中断）
		try:
			missing = check_voice_permissions(voice_channel)
			if missing:
				descs = [t(f"cmd.play.error.missing_permissions.{m}", voice_channel.mention) for m in missing]
				description = "- " + "\n- ".join(descs)
				await safe_edit(msg, embed=EmbedsTemplates.error(description=description))
				return
		except Exception:
			logger.error("事前権限チェック失敗")
			logger.error(traceback.format_exc())

		# VCへ接続 (残留接続があれば先に切断する)
		if await _leave_vc(voice_channel.guild):
			await asyncio.sleep(2)

		try:
			player = await voice_channel.connect(cls=sonolink.Player)
		except discord.errors.Forbidden:
			await _leave_vc(voice_channel.guild)
			try:
				retry_missing = check_voice_permissions(voice_channel)
			except Exception:
				retry_missing = []
			if retry_missing:
				descs = [t(f"cmd.play.error.missing_permissions.{m}", voice_channel.mention) for m in retry_missing]
				desc = "- " + "\n- ".join(descs)
			else:
				desc = t("cmd.play.error.voice_channel_forbidden", voice_channel.mention)
			await safe_edit(msg, embed=EmbedsTemplates.error(description=desc))
			return
		except discord.errors.NotFound:
			await _leave_vc(voice_channel.guild)
			await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.play.error.view_channel_missing")))
			return
		except TimeoutError:
			await _leave_vc(voice_channel.guild)
			try:
				retry_missing = check_voice_permissions(voice_channel)
			except Exception:
				retry_missing = []
			if retry_missing:
				descs = [t(f"cmd.play.error.missing_permissions.{m}", voice_channel.mention) for m in retry_missing]
				desc = "- " + "\n- ".join(descs)
			elif (
				voice_channel.user_limit is not None
				and voice_channel.user_limit != 0
				and len(voice_channel.members) >= voice_channel.user_limit
			):
				desc = t("cmd.play.error.voice_channel_full", voice_channel.mention)
			else:
				desc = t("cmd.play.cannot_connect_voice_channel")
			await safe_edit(msg, embed=EmbedsTemplates.error(description=desc))
			return
		except Exception:
			await _leave_vc(voice_channel.guild)
			if (
				voice_channel.user_limit is not None
				and voice_channel.user_limit != 0
				and len(voice_channel.members) >= voice_channel.user_limit
			):
				await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.play.error.voice_channel_full", voice_channel.mention)))
			else:
				await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.play.cannot_connect_voice_channel")))
			return

		# 検索ソース
		search_source = sonolink.TrackSourceType.YOUTUBE_MUSIC

		# 楽曲コンテナ (URLプレイリスト / DBプレイリスト共通)
		tracks: TrackCollection | None = None

		if query.startswith("playlist:"):
			# DB に保存されたプレイリストを読み込む
			playlist_id = query[len("playlist:") :]
			doc = await DBManager.col_playlists.find_one({"_id": playlist_id, "guild_id": guild.id})
			if doc is None:
				await _leave_vc(voice_channel.guild)
				await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.play.playlist_not_found")))
				return
			playlist = Playlist.from_doc(doc)
			if playlist is None:
				await _leave_vc(voice_channel.guild)
				await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.play.playlist_not_found")))
				return

			# 各楽曲を再検索して sonolink.Playable を再構築する (取得失敗した楽曲はスキップ)
			semaphore = asyncio.Semaphore(10)

			async def fetch_playlist_track(uri: str) -> SonoPlayable | None:
				async with semaphore:
					try:
						result = unpack_search(await client.sl_client.search_track(uri, source=search_source))
					except Exception:
						logger.exception("プレイリストの楽曲取得失敗: %s", uri)
						return None
					if result is None:
						logger.warning("プレイリストの楽曲が見つかりません: %s", uri)
						return None
					if isinstance(result, SonoPlaylist):
						candidates = result.tracks
					elif isinstance(result, SonoPlayable):
						candidates = [result]
					else:
						candidates = result
					if not candidates:
						logger.warning("プレイリストの楽曲が見つかりません: %s", uri)
						return None
					return next((t for t in candidates if t.uri == uri), candidates[0])

			# ponytail: 全曲を並列再検索 (上限500曲)。開始が数十秒かかる場合は上限引き下げか track_id 保存で緩和する
			playlist_tracks = [t for t in await asyncio.gather(*(fetch_playlist_track(t.uri) for t in playlist.tracks)) if t is not None]
			tracks = TrackCollection(tracks=playlist_tracks, name=playlist.name, plugin_info=None)
			if not tracks.tracks:
				await _leave_vc(voice_channel.guild)
				await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.play.no_tracks_found")))
				return
		else:
			# プレイリストを検索
			logger.debug(f"プレイリスト検索 - {search_source}: {query}")
			try:
				playlist_result = unpack_search(await client.sl_client.search_track(query, source=search_source))
			except Exception:
				await _leave_vc(voice_channel.guild)
				await safe_edit(
					msg,
					embed=EmbedsTemplates.internal_error(
						description=t("cmd.play.tracks_fetch_error"),
						error_code=await DebugLogger.report_internal_error(traceback.format_exc()),
					),
				)
				return

			# プレイリスト (楽曲) が見つからない場合
			if not playlist_result:
				await _leave_vc(voice_channel.guild)
				await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.play.no_tracks_found")))
				return
			# 指定されたクエリーがプレイリストではない場合
			if not isinstance(playlist_result, SonoPlaylist):
				await _leave_vc(voice_channel.guild)
				await safe_edit(msg, embed=EmbedsTemplates.error(description=t("cmd.play.not_a_playlist_url")))
				return

			tracks = TrackCollection(
				tracks=playlist_result.tracks,
				name=playlist_result.name,
				plugin_info=playlist_result.extras,
			)

		# クイズセッションを新規作成
		session = quiz_session_manager.create_session(guild.id, voice_channel.id, player, query, text_channel_id=text_channel_id)
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
		await safe_edit(
			msg,
			embed=EmbedsTemplates.info(
				title=t("cmd.play.preparing_complete.title"),
				description=t("cmd.play.preparing_complete.description", voice_channel.mention),
				icon="☑️",
			),
		)
		# クイズ開始
		play_result = await session.play(tracks, q_count, user.id, query)

		# 内部エラー
		if isinstance(play_result, str):
			await safe_edit(msg, embed=EmbedsTemplates.internal_error(error_code=play_result))

		# クイズセッションを終了する
		await quiz_session_manager.end_session(session.guild_id)

		# ボイスチャンネルから切断できていない場合は念の為切断する
		if voice_channel is not None:
			await _leave_vc(voice_channel.guild)

	except asyncio.CancelledError:
		raise
	except Exception:
		try:
			# クイズセッションを終了する
			if session is not None:
				await quiz_session_manager.end_session(session.guild_id)
		except Exception:
			logger.error("クイズ実行エラー - クイズ終了失敗")
			logger.error(traceback.format_exc())
		err_code = await DebugLogger.report_internal_error("クイズ実行エラー\n\n" + traceback.format_exc())
		# セッション確立前の失敗でもVC残留があり得るため best-effort で切断する
		await _leave_vc(guild)
		try:
			if inter.channel is not None and not isinstance(
				inter.channel, (discord.CategoryChannel, discord.ForumChannel, discord.MediaChannel)
			):
				await safe_send(inter.channel, embed=EmbedsTemplates.internal_error(error_code=err_code))
		except Exception:
			logger.exception("Internal Error Message Send Failed")
