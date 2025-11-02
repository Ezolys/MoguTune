import discord
from pycord.localizer import t


class Notification:
	@classmethod
	def info(cls, title: str, description: str = "") -> discord.Embed:
		"""情報表示用埋め込みメッセージ"""
		return discord.Embed(
			title=":information_source: " + title,
			description=description,
			colour=discord.Colour.from_rgb(74, 126, 183),
		)

	@classmethod
	def success(cls, title: str = "", description: str = "") -> discord.Embed:
		"""成功時用埋め込みメッセージ"""
		if title == "":
			title = t("embed.success.title")

		return discord.Embed(
			title=":white_check_mark: " + title,
			description=description,
			colour=discord.Colour.from_rgb(140, 176, 91),
		)

	@classmethod
	def warning(cls, title: str = "", description: str = "") -> discord.Embed:
		"""警告用埋め込みメッセージ"""
		if title == "":
			title = t("embed.warning.title")

		return discord.Embed(
			title=":warning: " + title,
			description=description,
			colour=discord.Colour.from_rgb(228, 146, 16),
		)

	@classmethod
	def error(cls, title: str = "", description: str = "") -> discord.Embed:
		"""エラー発生時用埋め込みメッセージ"""
		if title == "":
			title = t("embed.error.title")

		return discord.Embed(
			title=":no_entry_sign: " + title,
			description=description,
			colour=discord.Colour.from_rgb(247, 206, 80),
		)

	@classmethod
	def internal_error(cls, description: str | None = None, error_code: str | None = None) -> discord.Embed:
		"""内部エラー発生時用埋め込みメッセージ"""
		embed = discord.Embed(
			title=":closed_book: " + t("embed.internal_error.title"),
			description=description if description else t("embed.internal_error.description"),
			colour=discord.Colour.from_rgb(205, 61, 66),
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
			title=":pink_heart: " + t("donate.title"),
			description=t("donate.description"),
		)
		return embed
