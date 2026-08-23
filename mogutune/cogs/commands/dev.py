import logging

import discord
import mafic
from discord.ext import commands

from mogutune.embeds import EmbedsTemplates

logger = logging.getLogger(__name__)


class DevCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	async def get_node_labels(self, ctx: discord.AutocompleteContext) -> list[discord.OptionChoice]:
		"""ノードラベルの一覧を返す"""
		nodes: dict[str, mafic.Node] = mafic.NodePool.label_to_node  # pyright: ignore[reportAttributeAccessIssue]
		return [discord.OptionChoice(name=label, value=label) for label in nodes if ctx.value.lower() in label.lower()]

	@commands.slash_command()
	@discord.guild_only()
	@discord.default_permissions(administrator=True)
	@commands.cooldown(2, 5)
	@commands.is_owner()
	async def lavalink_node_info(
		self,
		ctx: discord.ApplicationContext,
		node_label: discord.Option(str, name="node", required=False, autocomplete=get_node_labels),  # pyright: ignore[reportInvalidTypeForm]
	) -> None:
		"""Lavalink ノードの情報を表示する"""
		await ctx.defer(ephemeral=True)

		nodes: dict[str, mafic.Node] = mafic.NodePool.label_to_node  # pyright: ignore[reportAttributeAccessIssue]
		if not nodes:
			await ctx.followup.send(embed=EmbedsTemplates.error(description="No nodes available"), ephemeral=True)
			return

		# ノード選択
		if node_label:
			node = nodes.get(node_label)
			if not node:
				await ctx.followup.send(embed=EmbedsTemplates.error(description=f"Node `{node_label}` not found"), ephemeral=True)
				return
			target_nodes = {node_label: node}
		else:
			target_nodes = nodes

		embeds: list[discord.Embed] = []
		for label, node in target_nodes.items():
			emb = discord.Embed(title=f"Node: {label}")
			status = "🟢 Available" if node.available else "🔴 Unavailable"
			emb.add_field(name="Status", value=status, inline=True)
			emb.add_field(name="Host", value=f"`{node.host}:{node.port}`", inline=True)
			emb.add_field(name="Lavalink Version", value=f"v{node.version}", inline=True)
			emb.add_field(name="Players", value=str(len(node.players)), inline=True)

			# 統計情報
			if node.stats:
				stats = node.stats
				mem_used = stats.memory.used / 1024 / 1024
				mem_alloc = stats.memory.allocated / 1024 / 1024
				uptime_h = int(stats.uptime.total_seconds() // 3600)
				uptime_m = int((stats.uptime.total_seconds() % 3600) // 60)

				emb.add_field(name="Playing", value=f"{stats.playing_player_count}/{stats.player_count}", inline=True)
				emb.add_field(name="Memory", value=f"{mem_used:.1f} / {mem_alloc:.1f} MB", inline=True)
				cpu = stats.cpu
				cpu_value = f"{cpu.cores} cores | sys: {cpu.system_load:.1f}% | ll: {cpu.lavalink_load:.1f}%"
				emb.add_field(name="CPU", value=cpu_value, inline=False)
				emb.add_field(name="Uptime", value=f"{uptime_h}h {uptime_m}m", inline=True)

			# /info エンドポイントからソース一覧を取得
			try:
				info = await node._Node__request("GET", "info")
				sources = info.get("sourceManagers", [])
				if sources:
					emb.add_field(name="Sources", value="`" + "`, `".join(sources) + "`", inline=False)
				plugins = info.get("plugins", [])
				if plugins:
					plugin_lines = [f"{p['name']} v{p['version']}" for p in plugins]
					emb.add_field(name="Plugins", value="\n".join(plugin_lines), inline=False)
			except Exception:
				logger.warning("Failed to fetch /info for node %s", label)

			embeds.append(emb)

		await ctx.followup.send(embeds=embeds, ephemeral=True)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(DevCommands(bot))
