# Copyright (c) 2026 Milkeyyy

import datetime
import logging
import traceback

import discord
import sonolink
import uuid_utils as uuid
from discord.ext import commands
from mogutune_core.db import DBManager
from pycord.localizer import t
from sonolink.models import Playable as SonoPlayable
from sonolink.models import Playlist as SonoPlaylist

from mogutune.client import client
from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.playlists import MAX_PLAYLISTS_PER_GUILD, Playlist
from mogutune.quiz.results import paginate_lines
from mogutune.track_adapter import unpack_search
from mogutune.url_query_labels import get_url_autocomplete_choice

logger = logging.getLogger(__name__)

LIST_PAGE_MAX_CHARS = 3800
"""一覧の1ページあたりの最大文字数 (埋め込み description の上限 4096 に余裕を持たせる)"""
LIST_PAGE_TIMEOUT_S = 120
"""一覧のページ送りのタイムアウト (秒)"""
AUTOCOMPLETE_LABEL_MAX = 100
"""オートコンプリートの選択肢ラベルの最大文字数"""


class PresetListView(discord.ui.View):
	"""登録済みプレイリスト一覧のページ送り"""

	def __init__(self, pages: list[str], author_id: int) -> None:
		super().__init__(timeout=LIST_PAGE_TIMEOUT_S)
		self.pages = pages
		self.author_id = author_id
		self.page = 0

		self.prev_button = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="⬅️", disabled=True)
		self.prev_button.callback = self.prev_button_callback
		self.page_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label=f"1/{len(pages)}", disabled=True)
		self.next_button = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="➡️")
		self.next_button.callback = self.next_button_callback
		self.add_item(self.prev_button)
		self.add_item(self.page_button)
		self.add_item(self.next_button)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		"""コマンド実行者以外のページ操作を拒否する"""
		if interaction.user is not None and interaction.user.id == self.author_id:
			return True
		await interaction.response.send_message(
			embed=EmbedsTemplates.error(description=t("cmd.playlist.list.not_author")),
			ephemeral=True,
			delete_after=3,
		)
		return False

	async def _show_page(self, interaction: discord.Interaction) -> None:
		"""現在のページを表示する"""
		self.prev_button.disabled = self.page == 0
		self.next_button.disabled = self.page >= len(self.pages) - 1
		self.page_button.label = f"{self.page + 1}/{len(self.pages)}"
		try:
			await interaction.response.edit_message(embed=self._embed(), view=self)
		except discord.errors.NotFound:
			pass

	def _embed(self) -> discord.Embed:
		return EmbedsTemplates.info(title=t("cmd.playlist.list.title"), description=self.pages[self.page], icon="📋")

	async def prev_button_callback(self, interaction: discord.Interaction) -> None:
		if self.page > 0:
			self.page -= 1
		await self._show_page(interaction)

	async def next_button_callback(self, interaction: discord.Interaction) -> None:
		if self.page < len(self.pages) - 1:
			self.page += 1
		await self._show_page(interaction)


class PlaylistCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	preset = discord.SlashCommandGroup(
		"preset",
		"お気に入りのプレイリストを登録・管理します。",
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

	async def _fetch(self, url: str) -> SonoPlayable | list[SonoPlayable] | SonoPlaylist | None:
		"""URL を Lavalink で解決する (失敗時は None)"""
		try:
			return unpack_search(await client.sl_client.search_track(url, source=sonolink.TrackSourceType.YOUTUBE_MUSIC))
		except Exception:
			logger.exception("楽曲取得失敗: %s", url)
			return None

	@preset.command(name="add")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def add_playlist(
		self,
		ctx: discord.ApplicationContext,
		url: discord.Option(str, required=True, autocomplete=get_url_choice),  # pyright: ignore[reportInvalidTypeForm]
		name: discord.Option(str, required=False),  # pyright: ignore[reportInvalidTypeForm]
		description: discord.Option(str, required=False),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""お気に入りのプレイリストを登録する"""
		# ギルド限定コマンドのため guild_id は必ず存在する
		assert ctx.guild_id is not None  # noqa: S101
		try:
			# URL 解決に時間がかかってもよいように先に応答を保留する (3秒制限対策)
			await ctx.defer(ephemeral=True)

			# ギルドごとの上限チェック
			playlist_count = await DBManager.col_playlists.count_documents({"guild_id": ctx.guild_id})
			if playlist_count >= MAX_PLAYLISTS_PER_GUILD:
				await ctx.followup.send(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.guild_limit")),
					ephemeral=True,
				)
				return

			# 同じ URL の重複登録チェック
			if await DBManager.col_playlists.find_one({"guild_id": ctx.guild_id, "url": url}) is not None:
				await ctx.followup.send(
					embed=EmbedsTemplates.warning(description=t("cmd.playlist.add.error.already_registered")),
					ephemeral=True,
				)
				return

			# URL を解決してプレイリストか検証する (曲リストは保存せず曲数のみ記録する)
			result = await self._fetch(url)
			if not isinstance(result, SonoPlaylist):
				await ctx.followup.send(
					embed=EmbedsTemplates.error(description=t("cmd.play.not_a_playlist_url")),
					ephemeral=True,
				)
				return

			track_count = len(result.tracks)
			preset_name = (name or "").strip() or result.name
			doc = {
				"_id": str(uuid.uuid7()),
				"guild_id": ctx.guild_id,
				"name": preset_name,
				"description": (description or "").strip(),
				"url": url,
				"track_count": track_count,
				"author_id": ctx.author.id,
				"created_at": datetime.datetime.now(tz=datetime.UTC),
			}
			await DBManager.col_playlists.insert_one(doc)

			await ctx.followup.send(
				embed=EmbedsTemplates.success(description=t("cmd.playlist.add.registered", preset_name, track_count, url)),
				ephemeral=True,
			)
		except Exception:
			logger.exception("プレイリスト登録エラー")
			await ctx.followup.send(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)

	@preset.command(name="list")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def list_playlists(self, ctx: discord.ApplicationContext) -> None:
		"""登録済みのプレイリスト一覧を表示する"""
		# ギルド限定コマンドのため guild_id は必ず存在する
		assert ctx.guild_id is not None  # noqa: S101
		try:
			docs = (
				await DBManager.col_playlists.find({"guild_id": ctx.guild_id}).sort("created_at", 1).to_list(length=MAX_PLAYLISTS_PER_GUILD)
			)
			playlists = [pl for pl in (Playlist.from_doc(doc) for doc in docs) if pl is not None]
			if not playlists:
				await ctx.respond(
					embed=EmbedsTemplates.info(description=t("cmd.playlist.list.empty")),
					ephemeral=True,
				)
				return

			lines = [t("cmd.playlist.list.line", pl.name, pl.track_count, pl.url) for pl in playlists]
			pages = paginate_lines(lines, LIST_PAGE_MAX_CHARS)
			view = PresetListView(pages, ctx.author.id) if len(pages) > 1 else None
			await ctx.respond(
				embed=EmbedsTemplates.info(title=t("cmd.playlist.list.title"), description=pages[0], icon="📋"),
				view=view,
			)
		except Exception:
			logger.exception("プレイリスト一覧表示エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)

	@preset.command(name="edit")
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

	@preset.command(name="delete")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def delete_playlist(
		self,
		ctx: discord.ApplicationContext,
		playlist: discord.Option(str, required=True, autocomplete=get_playlists),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""プレイリストの登録を解除する"""
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

	@preset.command(name="detail")
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
			pl = Playlist.from_doc(doc)
			if pl is None:
				await ctx.respond(
					embed=EmbedsTemplates.error(description=t("cmd.playlist.error.not_found")),
					ephemeral=True,
				)
				return

			# 登録者名を取得 (在籍していない場合は ID を表示)
			author_label = str(pl.author_id)
			if ctx.guild is not None:
				member = await ctx.guild.get_or_fetch(discord.Member, pl.author_id)
				if member is not None:
					author_label = member.mention

			embed = EmbedsTemplates.info(title=t("cmd.playlist.detail.title"), icon="📋")
			embed.add_field(name=t("cmd.playlist.detail.name"), value=pl.name, inline=False)
			embed.add_field(name=t("cmd.playlist.detail.description"), value=pl.description or "-", inline=False)
			embed.add_field(name=t("cmd.playlist.detail.url"), value=pl.url, inline=False)
			embed.add_field(name=t("cmd.playlist.detail.author"), value=author_label, inline=True)
			embed.add_field(name=t("cmd.playlist.detail.created_at"), value=f"<t:{int(pl.created_at.timestamp())}:f>", inline=True)
			embed.add_field(name=t("cmd.playlist.detail.track_count"), value=str(pl.track_count), inline=True)

			await ctx.respond(embed=embed)
		except Exception:
			logger.exception("プレイリスト詳細表示エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(PlaylistCommands(bot))
