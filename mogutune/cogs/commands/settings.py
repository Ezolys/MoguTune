# Copyright (c) 2026 Milkeyyy

import dataclasses
import logging
import traceback

import discord
from discord.ext import commands
from pycord.localizer import t

from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.settings import GuildSettings, guild_settings_manager

logger = logging.getLogger(__name__)


class SettingsCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	settings = discord.SlashCommandGroup(
		"settings",
		"クイズの設定を表示・変更します。",
		default_member_permissions=discord.Permissions(manage_guild=True),
	)

	@settings.command()
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def show(self, ctx: discord.ApplicationContext) -> None:
		"""現在の設定を表示する"""
		# ギルド設定のみを対象とする (guild_only により実行時は必ず int)
		assert ctx.guild_id is not None  # noqa: S101
		try:
			settings = await guild_settings_manager.get(ctx.guild_id)
			fields = dataclasses.fields(GuildSettings)
			if not fields:
				await ctx.respond(
					embed=EmbedsTemplates.info(
						title=t("cmd.settings.show.title"),
						description=t("cmd.settings.show.no_items"),
						icon="⚙️",
					)
				)
				return
			await ctx.respond(
				embed=EmbedsTemplates.info(
					title=t("cmd.settings.show.title"),
					description="\n".join(self._format_setting(f, settings) for f in fields),
					icon="⚙️",
				)
			)
		except Exception:
			logger.exception("設定表示エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc()))
			)

	@settings.command(name="set")
	@discord.guild_only()
	@commands.cooldown(2, 5)
	async def set_settings(
		self,
		ctx: discord.ApplicationContext,
		artist_in_answers: discord.Option(bool, required=False),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""設定を変更する"""
		# ギルド設定のみを対象とする (guild_only により実行時は必ず int)
		assert ctx.guild_id is not None  # noqa: S101
		if not dataclasses.fields(GuildSettings):
			await ctx.respond(
				embed=EmbedsTemplates.info(
					title=t("cmd.settings.show.title"),
					description=t("cmd.settings.set.no_items"),
					icon="⚙️",
				),
				ephemeral=True,
			)
			return

		kwargs: dict[str, object] = {}
		if artist_in_answers is not None:
			kwargs["artist_in_answers"] = artist_in_answers
		if not kwargs:
			await ctx.respond(
				embed=EmbedsTemplates.warning(description=t("cmd.settings.set.no_options")),
				ephemeral=True,
			)
			return

		try:
			settings = await guild_settings_manager.set(ctx.guild_id, **kwargs)
		except ValueError as e:
			await ctx.respond(embed=EmbedsTemplates.error(description=str(e)), ephemeral=True)
			return
		except Exception:
			logger.exception("設定変更エラー")
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc())),
				ephemeral=True,
			)
			return

		await ctx.respond(
			embed=EmbedsTemplates.success(
				title=t("cmd.settings.set.updated"),
				description="\n".join(self._format_setting(f, settings) for f in dataclasses.fields(GuildSettings)),
				icon="⚙️",
			)
		)

	@staticmethod
	def _format_setting(field: dataclasses.Field, settings: GuildSettings) -> str:
		"""設定項目の表示行を生成する"""
		value = getattr(settings, field.name)
		label = str(value)
		if isinstance(value, bool):
			label = t("cmd.settings.value.enabled") if value else t("cmd.settings.value.disabled")
		return f"**{t(f'cmd.settings.item.{field.name}')}**: {label}"


def setup(bot: discord.Bot) -> None:
	bot.add_cog(SettingsCommands(bot))
