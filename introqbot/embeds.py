import discord
import localizations
from localizations import _


class Notification:
	@classmethod
	def success(cls, title: str = "", description: str = "", lang: str = "") -> discord.Embed:
		"""成功時用埋め込みメッセージ"""
		if title == "":
			title = _("CmdMsg_Success") if lang.strip() == "" else localizations.translate("CmdMsg_Success", lang=lang)

		return discord.Embed(
			title=":white_check_mark: " + title,
			description=description,
			colour=discord.Colour.from_rgb(140, 176, 91),
		)

	@classmethod
	def warning(cls, title: str = "", description: str = "", lang: str = "") -> discord.Embed:
		"""警告用埋め込みメッセージ"""
		if title == "":
			title = _("CmdMsg_Warning") if lang.strip() == "" else localizations.translate("CmdMsg_Warning", lang=lang)

		return discord.Embed(
			title=":warning: " + title,
			description=description,
			colour=discord.Colour.from_rgb(228, 146, 16),
		)

	@classmethod
	def error(cls, title: str = "", description: str = "", lang: str = "") -> discord.Embed:
		"""エラー発生時用埋め込みメッセージ"""
		if title == "":
			title = _("CmdMsg_ExcutionError") if lang.strip() == "" else localizations.translate("CmdMsg_ExcutionError", lang=lang)

		return discord.Embed(
			title=":no_entry_sign: " + title,
			description=description,
			colour=discord.Colour.from_rgb(247, 206, 80),
		)

	@classmethod
	def internal_error(cls, description: str | None = None, error_code: str | None = None) -> discord.Embed:
		"""内部エラー発生時用埋め込みメッセージ"""
		embed = discord.Embed(
			title=":closed_book: " + _("CmdMsg_InternalError"),
			description=description if description else _("CmdMsg_InternalError_Description"),
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
			title=":pink_heart: " + _("DonationEmbed_Title"),
			description=_("DonationEmbed_Description"),
		)
		return embed
