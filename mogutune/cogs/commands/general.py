import datetime
import logging
import traceback
from os import getenv

import discord
from discord.ext import commands
from mogutune_core import ranking
from mogutune_core.models import Player
from pycord.localizer import t

from mogutune import leaderboard
from mogutune.app import App
from mogutune.client import client
from mogutune.debug_logger import DebugLogger
from mogutune.embeds import EmbedsTemplates
from mogutune.quiz import quiz_session_manager
from mogutune.quiz.results import LIST_MAX_CHARS, rank_icon, truncate_lines

logger = logging.getLogger(__name__)


class GeneralCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	async def ping(self, ctx: discord.ApplicationContext) -> None:
		ping = round(client.latency * 1000)
		await ctx.respond(embed=EmbedsTemplates.success(title="Ping", description=t("cmd.ping.result", ping)))

	@commands.slash_command()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def about(self, ctx: discord.ApplicationContext) -> None:
		try:
			embed = discord.Embed(color=discord.Colour.blue())
			embed.set_author(name=App.NAME, icon_url=client.user.display_avatar.url)
			embed.set_footer(text=App.COPYRIGHT)
			embed.add_field(
				name="Version",
				value=f"`{App.VERSION_STRING}` (`{App.get_git_commit_hash()[0:7]}`)",
			)
			embed.add_field(
				name="Developer",
				value=f"- {App.DEVELOPER_NAME}\n\
  - [Website]({App.DEVELOPER_WEBSITE_URL})\n\
  - [Twitter]({App.DEVELOPER_TWITTER_URL})",
				inline=False,
			)
			await ctx.respond(embeds=[embed])
		except Exception:
			logger.error(traceback.format_exc())
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc()))
			)

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def sessions(self, ctx: discord.ApplicationContext) -> None:
		try:
			active_sessions = len(quiz_session_manager.sessions)
			max_sessions = int(getenv("MAX_SESSIONS", "0"))
			logger.info(getenv("MAX_SESSIONS"))

			limit_str = t("cmd.sessions.result.limit_none")
			if max_sessions > 0:
				limit_str = f"{max_sessions}"

			now = int(datetime.datetime.now().timestamp())

			embed = EmbedsTemplates.info(
				title=t("cmd.sessions.result.title"),
				description=f"{t('cmd.sessions.result.last_update')}: <t:{now}:f> (<t:{now}:R>)",
				icon="📊",
			)
			embed.add_field(name=t("cmd.sessions.result.current"), value=f"`{active_sessions}` / `{limit_str}`")
			await ctx.respond(embed=embed)
		except Exception:
			logger.error(traceback.format_exc())
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc()))
			)

	async def _leaderboard_lines(self, guild: discord.Guild, entries: list[leaderboard.LeaderboardEntry]) -> list[str]:
		"""リーダーボードの表示行を生成する (順位付けは core のランキングロジックを再利用する)"""
		ranked = ranking.build_ranking([Player(id=e.user_id, point=e.correct) for e in entries])
		entry_by_id = {e.user_id: e for e in entries}
		lines: list[str] = []
		for rank_entry in ranked:
			entry = entry_by_id[rank_entry.player_id]
			member: discord.Member | None = await guild.get_or_fetch(discord.Member, entry.user_id)
			name = (member.mention or member.display_name) if member is not None else str(entry.user_id)
			lines.append(
				t(
					"cmd.leaderboard.result.line",
					rank_icon(rank_entry.rank),
					name,
					entry.correct,
					f"{leaderboard.accuracy_percent(entry.correct, entry.questions):.1f}",
				)
			)
		return lines

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(send_messages=True)
	@commands.cooldown(2, 5)
	async def leaderboard(
		self,
		ctx: discord.ApplicationContext,
		limit: discord.Option(int, min_value=1, max_value=25, required=False, default=10),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""このサーバーのクイズのリーダーボードを表示する"""
		assert ctx.guild_id is not None  # noqa: S101
		assert ctx.guild is not None  # noqa: S101
		try:
			entries = await leaderboard.fetch_top(ctx.guild_id, limit)
			if not entries:
				await ctx.respond(
					embed=EmbedsTemplates.info(
						title=t("cmd.leaderboard.result.title"),
						description=t("cmd.leaderboard.result.empty"),
						icon="🏆",
					)
				)
				return

			kept, omitted = truncate_lines(await self._leaderboard_lines(ctx.guild, entries), LIST_MAX_CHARS)
			if omitted:
				kept.append(t("msg.q.others", omitted))

			embed = EmbedsTemplates.info(
				title=t("cmd.leaderboard.result.title"),
				description="\n".join(kept),
				icon="🏆",
			)

			# 実行者自身の順位をフッターへ表示する
			rank, my_entry = await leaderboard.fetch_rank(ctx.guild_id, ctx.user.id)
			if my_entry is None:
				embed.set_footer(text=t("cmd.leaderboard.result.no_record"))
			else:
				embed.set_footer(
					text=t(
						"cmd.leaderboard.result.you",
						rank,
						my_entry.correct,
						f"{leaderboard.accuracy_percent(my_entry.correct, my_entry.questions):.1f}",
					)
				)
			await ctx.respond(embed=embed)
		except Exception:
			logger.error(traceback.format_exc())
			await ctx.respond(
				embed=EmbedsTemplates.internal_error(error_code=await DebugLogger.report_internal_error(traceback.format_exc()))
			)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(GeneralCommands(bot))
