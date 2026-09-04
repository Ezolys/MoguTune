import logging

import discord
import sonolink
from discord.ext import commands

from mogutune.client import client
from mogutune.embeds import EmbedsTemplates

logger = logging.getLogger(__name__)


async def build_node_embed(label: str, node: sonolink.Node) -> discord.Embed:
	"""単一ノードの情報 Embed を生成する"""
	emb = discord.Embed(title=f"Node: {label}")
	if node.is_connected:
		status = "🟢 Connected"
	elif node.is_connecting:
		status = "🟡 Connecting"
	else:
		status = "🔴 Disconnected"
	emb.add_field(name="Status", value=status, inline=True)
	emb.add_field(name="URI", value=f"`{node.uri}`", inline=True)

	# /info エンドポイントからバージョン・ソース・プラグイン一覧を取得
	try:
		info = await node.fetch_info()
		emb.add_field(name="Lavalink Version", value=f"v{info.version.semver}", inline=True)
		if info.source_managers:
			emb.add_field(name="Sources", value="`" + "`, `".join(info.source_managers) + "`", inline=False)
		if info.plugins:
			plugin_lines = [f"{p.name} v{p.version}" for p in info.plugins]
			emb.add_field(name="Plugins", value="\n".join(plugin_lines), inline=False)
	except Exception:
		logger.warning("Failed to fetch /info for node %s", label)

	# プレイヤー数
	try:
		players = await node.fetch_players()
		emb.add_field(name="Players", value=str(len(players)), inline=True)
	except Exception:
		logger.warning("Failed to fetch players for node %s", label)

	# 統計情報
	stats = node.stats
	if stats is not None:
		uptime = stats.uptime
		total_seconds = uptime / 1000 if isinstance(uptime, (int, float)) else uptime.total_seconds()
		uptime_h = int(total_seconds // 3600)
		uptime_m = int((total_seconds % 3600) // 60)

		mem_used = stats.memory.used / 1024 / 1024
		mem_alloc = stats.memory.allocated / 1024 / 1024

		emb.add_field(name="Playing", value=f"{stats.playing_players}/{stats.players}", inline=True)
		emb.add_field(name="Memory", value=f"{mem_used:.1f} / {mem_alloc:.1f} MB", inline=True)
		cpu = stats.cpu
		cpu_value = f"{cpu.cores} cores | sys: {cpu.system_load:.1f}% | ll: {cpu.lavalink_load:.1f}%"
		emb.add_field(name="CPU", value=cpu_value, inline=False)
		emb.add_field(name="Uptime", value=f"{uptime_h}h {uptime_m}m", inline=True)

	return emb


class DevCommands(discord.Cog):
	def __init__(self, bot: discord.Bot) -> None:
		self.bot = bot

	async def get_node_labels(self, ctx: discord.AutocompleteContext) -> list[discord.OptionChoice]:
		"""登録済み Lavalink node の ID 一覧を返す"""
		nodes = {n.id: n for n in client.sl_client.nodes}
		return [discord.OptionChoice(name=node_id, value=node_id) for node_id in nodes if ctx.value.lower() in node_id.lower()]

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

		nodes = {n.id: n for n in client.sl_client.nodes}
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
			embeds.append(await build_node_embed(label, node))

		await ctx.followup.send(embeds=embeds, ephemeral=True)


def setup(bot: discord.Bot) -> None:
	bot.add_cog(DevCommands(bot))
