import discord
from pycord.localizer import t


class EmbedsTemplates:
	@classmethod
	def info(cls, title: str, description: str = "", icon: str = ":information_source:") -> discord.Embed:
		"""情報表示用埋め込みメッセージ"""
		return discord.Embed(
			title=icon + " " + title,
			description=description,
			colour=discord.Colour.from_rgb(74, 126, 183),
		)

	@classmethod
	def success(cls, title: str = "", description: str = "", icon: str = ":white_check_mark:") -> discord.Embed:
		"""成功時用埋め込みメッセージ"""
		if title == "":
			title = t("embed.success.title")

		return discord.Embed(
			title=icon + " " + title,
			description=description,
			colour=discord.Colour.from_rgb(140, 176, 91),
		)

	@classmethod
	def warning(cls, title: str = "", description: str = "", icon: str = ":warning:") -> discord.Embed:
		"""警告用埋め込みメッセージ"""
		if title == "":
			title = t("embed.warning.title")

		return discord.Embed(
			title=icon + " " + title,
			description=description,
			colour=discord.Colour.from_rgb(255, 204, 77),
		)

	@classmethod
	def error(cls, title: str = "", description: str = "", icon: str = ":no_entry_sign:") -> discord.Embed:
		"""エラー発生時用埋め込みメッセージ"""
		if title == "":
			title = t("embed.error.title")

		return discord.Embed(
			title=icon + " " + title,
			description=description,
			colour=discord.Colour.from_rgb(221, 46, 68),
		)

	@classmethod
	def internal_error(cls, description: str | None = None, error_code: str | None = None) -> discord.Embed:
		"""内部エラー発生時用埋め込みメッセージ"""
		embed = discord.Embed(
			title=":closed_book: " + t("embed.internal_error.title"),
			description=description if description else t("embed.internal_error.description"),
			colour=discord.Colour.from_rgb(221, 46, 68),
		)
		# エラーコードが渡された場合は先頭に挿入する
		if error_code:
			embed.description = f"{embed.description}\n\n> :pencil: Error Code\n> ```{error_code}```"
		return embed


class Donation:
	@classmethod
	async def donation(cls) -> discord.Embed:
		embed = discord.Embed(
			colour=discord.colour.Colour.nitro_pink(),
			title=":pink_heart: " + t("embed.donate.title"),
			description=t("embed.donate.description"),
		)
		return embed
