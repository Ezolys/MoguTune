# Copyright (c) 2026 Milkeyyy

import datetime
import logging
import traceback

import discord
import mafic
import uuid_utils as uuid
from discord.ext import commands
from mogutune_core import trackpool
from mogutune_core.db import DBManager
from pycord.localizer import t

from mogutune.client import client
from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.playlists import (
	MAX_PLAYLISTS_PER_GUILD,
	MAX_TRACKS_PER_PLAYLIST,
	Playlist,
	dedupe_track_docs,
)
from mogutune.quiz.track_adapter import to_core_tracks, to_mafic_tracks, to_stored_track_dict
from mogutune.url_query_labels import get_url_autocomplete_choice

logger = logging.getLogger(__name__)

DETAIL_TRACK_LIST_MAX = 10
"""プレイリスト詳細で一覧表示する楽曲数の上限"""
AUTOCOMPLETE_LABEL_MAX = 100
"""オートコンプリートの選択肢ラベルの最大文字数"""


class PlaylistCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	playlist = discord.SlashCommandGroup(
		"playlist",
		"プレイリストを管理します。",
		default_member_permissions=discord.Permissions(manage_guild=True),
	)

	async def get_playlists(self, ctx: discord.AutocompleteContext) -> list[discord.OptionChoice]:
		"""サーバーのプレイリスト一覧を返す (入力内容で名前を絞り込む)"""
		guild_id = ctx.interaction.guild_id
		if guild_id is None:
			return []
		query: dict[str, object] = {"guild_id": guild_id}
		if ctx.value != "":
			query["name"] = {"$regex": ctx.value, "$options": "i"}
		docs = await DBManager.col_playlists.find(query).to_list(length=MAX_PLAYLISTS_PER_GUILD)
		choices: list[discord.OptionChoice] = []
		for doc in docs:
			name = doc.get("name", "")
			desc = doc.get("description", "")
			label = f"{name} | {desc}" if isinstance(desc, str) and desc != "" else name
			if len(label) > AUTOCOMPLETE_LABEL_MAX:
				label = label[:AUTOCOMPLETE_LABEL_MAX]
			choices.append(discord.OptionChoice(name=label, value=str(doc.get("_id", ""))))
		return choices

	async def get_url_choice(self, ctx: discord.AutocompleteContext) -> list[discord.OptionChoice]:
		"""URL の種別ラベルを返す (既存の /play と同じ判定を利用)"""
		if ctx.value == "":
			return []
		choice = get_url_autocomplete_choice(ctx.value, str(ctx.interaction.locale) if ctx.interaction else None)
		if choice is not None:
			label, value = choice
			return [discord.OptionChoice(name=label, value=value)]
		return []

	async def _fetch(self, url: str) -> list[mafic.Track] | mafic.Playlist | None:
		"""URL を Lavalink で解決する (失敗時は None)"""
		try:
			return await client.pool.get_random_node().fetch_tracks(url, search_type=mafic.SearchType.YOUTUBE_MUSIC)
		except Exception:
			logger.exception("楽曲取得失敗: %s", url)
			return None

	async def _fetch_single_track_doc(self, url: str) -> dict | None:
		"""単一トラックの URL を解決して保存用サブドキュメントを返す (単一トラックでない・失敗時は None)"""
		result = await self._fetch(url)
		if not isinstance(result, list) or not result:
			return None
		return to_stored_track_dict(result[0])

	async def _fetch_playlist_track_docs(self, url: str) -> list[dict] | None:
		"""プレイリスト URL を解決して保存用サブドキュメントの一覧を返す (単一トラック・失敗時は None)"""
		result = await self._fetch(url)
		if not isinstance(result, mafic.Playlist):
			return None
		# 重複した楽曲を除く (core で判定し、URI で mafic.Track へ引き戻す)
		unique_core_tracks = trackpool.dedupe(to_core_tracks(result.tracks))
		unique_mafic_tracks = to_mafic_tracks(unique_core_tracks, result.tracks)
		return [to_stored_track_dict(t) for t in unique_mafic_tracks]

	@playlist.command(name="new")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def new_playlist(
		self,
		ctx: discord.ApplicationContext,
		name: discord.Option(str, required=True),  # pyright: ignore[reportInvalidTypeForm]
		description: discord.Option(str, required=True),  # pyright: ignore[reportInvalidTypeForm]
		uri: discord.Option(str, required=False, autocomplete=get_url_choice),  # pyright: ignore[reportInvalidTypeForm]
		tracks: discord.Option(str, required=False),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""プレイリストを新規作成する"""
		# ギルド限定コマンドのため guild_id は必ず存在する
		assert ctx.guild_id is not None  # noqa: S101
		try:
			# ギルドごとの上限チェック
			playlist_count = await DBManager.col_playlists.count_documents({"guild_id": ctx.guild_id})
			if playlist_count >= MAX_PLAYLISTS_PER_GUILD:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.guild_limit")),
					ephemeral=True,
				)
				return

			# uri (プレイリスト) と tracks (楽曲) の一覧を取得してマージする
			track_docs: list[dict] = []
			if uri is not None:
				_uri_tracks = await self._fetch_playlist_track_docs(uri)
				if _uri_tracks is None:
					await ctx.respond(
						embed=EmbedsTemplates.error(description=t("cmd.play.not_a_playlist_url")),
						ephemeral=True,
					)
					return
				track_docs.extend(_uri_tracks)
			if tracks is not None:
				for url in tracks.split():
					track_doc = await self._fetch_single_track_doc(url)
					if track_doc is not None:
						track_docs.append(track_doc)
			track_docs = dedupe_track_docs(track_docs)

			# 楽曲数上限チェック
			if len(track_docs) > MAX_TRACKS_PER_PLAYLIST:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.track_limit")),
					ephemeral=True,
				)
				return

			doc = {
				"_id": str(uuid.uuid7()),
				"guild_id": ctx.guild_id,
				"name": name,
				"description": description,
				"author_id": ctx.author.id,
				"created_at": datetime.datetime.now(tz=datetime.UTC),
				"tracks": track_docs,
			}
			await DBManager.col_playlists.insert_one(doc)

			if track_docs:
				await ctx.respond(embed=EmbedsTemplates.success(description=t("cmd.playlist.new.created", name, len(track_docs))))
			else:
				await ctx.respond(embed=EmbedsTemplates.success(description=t("cmd.playlist.new.created_empty", name)))
		except Exception:
			logger.exception("プレイリスト作成エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)

	@playlist.command(name="add")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def add_tracks(
		self,
		ctx: discord.ApplicationContext,
		playlist: discord.Option(str, required=True, autocomplete=get_playlists),  # pyright: ignore[reportInvalidTypeForm]
		urls: discord.Option(str, required=True),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""プレイリストに楽曲を追加する"""
		# ギルド限定コマンドのため guild_id は必ず存在する
		assert ctx.guild_id is not None  # noqa: S101
		try:
			doc = await DBManager.col_playlists.find_one({"_id": playlist, "guild_id": ctx.guild_id})
			if doc is None:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.not_found")),
					ephemeral=True,
				)
				return

			existing_uris = {t.get("uri") for t in doc.get("tracks", []) if isinstance(t, dict) and isinstance(t.get("uri"), str)}
			valid_docs: list[dict] = []
			valid_uris: set[str] = set()
			skipped = 0
			for url in urls.split():
				track_doc = await self._fetch_single_track_doc(url)
				uri = track_doc.get("uri") if track_doc is not None else None
				if track_doc is None or not isinstance(uri, str) or uri in existing_uris or uri in valid_uris:
					skipped += 1
					continue
				valid_docs.append(track_doc)
				valid_uris.add(uri)

			if not valid_docs:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.add.error.no_valid_tracks")),
					ephemeral=True,
				)
				return

			# 楽曲数上限チェック (追加後の合計が上限を超える場合は何も追加しない)
			if len(existing_uris) + len(valid_docs) > MAX_TRACKS_PER_PLAYLIST:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.track_limit")),
					ephemeral=True,
				)
				return

			await DBManager.col_playlists.update_one(
				{"_id": playlist, "guild_id": ctx.guild_id},
				{"$push": {"tracks": {"$each": valid_docs}}},
			)
			await ctx.respond(embed=EmbedsTemplates.success(description=t("cmd.playlist.add.result", len(valid_docs), skipped)))
		except Exception:
			logger.exception("プレイリスト楽曲追加エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)

	@playlist.command(name="edit")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def edit_playlist(
		self,
		ctx: discord.ApplicationContext,
		playlist: discord.Option(str, required=True, autocomplete=get_playlists),  # pyright: ignore[reportInvalidTypeForm]
		name: discord.Option(str, required=False),  # pyright: ignore[reportInvalidTypeForm]
		description: discord.Option(str, required=False),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""プレイリストの名前・説明を編集する"""
		# ギルド限定コマンドのため guild_id は必ず存在する
		assert ctx.guild_id is not None  # noqa: S101
		try:
			update: dict[str, str] = {}
			if name is not None:
				update["name"] = name
			if description is not None:
				update["description"] = description
			if not update:
				await ctx.respond(
					embed=EmbedsTemplates.warning(description=t("cmd.playlist.edit.nothing_specified")),
					ephemeral=True,
				)
				return

			result = await DBManager.col_playlists.update_one(
				{"_id": playlist, "guild_id": ctx.guild_id},
				{"$set": update},
			)
			if result.matched_count == 0:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.not_found")),
					ephemeral=True,
				)
				return
			await ctx.respond(embed=EmbedsTemplates.success(description=t("cmd.playlist.edit.updated")))
		except Exception:
			logger.exception("プレイリスト編集エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)

	@playlist.command(name="delete")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def delete_playlist(
		self,
		ctx: discord.ApplicationContext,
		playlist: discord.Option(str, required=True, autocomplete=get_playlists),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""プレイリストを削除する"""
		# ギルド限定コマンドのため guild_id は必ず存在する
		assert ctx.guild_id is not None  # noqa: S101
		try:
			result = await DBManager.col_playlists.delete_one({"_id": playlist, "guild_id": ctx.guild_id})
			if result.deleted_count == 0:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.not_found")),
					ephemeral=True,
				)
				return
			await ctx.respond(embed=EmbedsTemplates.success(description=t("cmd.playlist.delete.deleted")))
		except Exception:
			logger.exception("プレイリスト削除エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)

	@playlist.command(name="detail")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def detail_playlist(
		self,
		ctx: discord.ApplicationContext,
		playlist: discord.Option(str, required=True, autocomplete=get_playlists),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""プレイリストの詳細を表示する"""
		# ギルド限定コマンドのため guild_id は必ず存在する
		assert ctx.guild_id is not None  # noqa: S101
		try:
			doc = await DBManager.col_playlists.find_one({"_id": playlist, "guild_id": ctx.guild_id})
			if doc is None:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.not_found")),
					ephemeral=True,
				)
				return
			pl = Playlist.from_doc(doc)
			if pl is None:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.not_found")),
					ephemeral=True,
				)
				return

			# 作成者名を取得 (在籍していない場合は ID を表示)
			author_label = str(pl.author_id)
			if ctx.guild is not None:
				member = await ctx.guild.get_or_fetch(discord.Member, pl.author_id)
				if member is not None:
					author_label = member.mention

			embed = EmbedsTemplates.info(title=t("cmd.playlist.detail.title"), icon="📋")
			embed.add_field(name=t("cmd.playlist.detail.name"), value=pl.name, inline=False)
			embed.add_field(name=t("cmd.playlist.detail.description"), value=pl.description or "-", inline=False)
			embed.add_field(name=t("cmd.playlist.detail.author"), value=author_label, inline=True)
			embed.add_field(name=t("cmd.playlist.detail.created_at"), value=f"<t:{int(pl.created_at.timestamp())}:f>", inline=True)
			embed.add_field(name=t("cmd.playlist.detail.track_count"), value=str(len(pl.tracks)), inline=True)

			if pl.tracks:
				lines = []
				for track in pl.tracks[:DETAIL_TRACK_LIST_MAX]:
					title = track.title if track.title != "" else track.uri
					label = f"{title} - {track.author}" if track.author != "" else title
					lines.append(f"- {label}")
				if len(pl.tracks) > DETAIL_TRACK_LIST_MAX:
					lines.append(t("cmd.playlist.detail.tracks_more", len(pl.tracks) - DETAIL_TRACK_LIST_MAX))
				embed.add_field(name=t("cmd.playlist.detail.tracks"), value="\n".join(lines), inline=False)
			else:
				embed.add_field(name=t("cmd.playlist.detail.tracks"), value=t("cmd.playlist.detail.tracks_empty"), inline=False)

			await ctx.respond(embed=embed)
		except Exception:
			logger.exception("プレイリスト詳細表示エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(PlaylistCommands(bot))
