# Copyright (c) 2026 Milkeyyy

import logging

import aiohttp
import discord

logger = logging.getLogger(__name__)

_SEND_ERRORS: tuple[type[BaseException], ...] = (
	RuntimeError,  # aiohttp セッション切断時 ("Session is closed" 等)
	aiohttp.ClientConnectionError,
	discord.HTTPException,  # NotFound / Forbidden / 429 等を含む
)
"""送信失敗として握りつぶす例外 (想定内の障害・シャットダウン競合)"""


async def safe_edit(msg: discord.Message | discord.WebhookMessage, /, **kwargs: object) -> bool:
	"""メッセージ編集の best-effort 版 (失敗時はログのみ残し False を返す)"""
	try:
		await msg.edit(**kwargs)
	except _SEND_ERRORS as e:
		logger.warning("メッセージ編集失敗 (%s): %s", type(e).__name__, e)
		return False
	except Exception:
		logger.exception("メッセージ編集失敗")
		return False
	return True


async def safe_send(channel: discord.abc.Messageable, /, **kwargs: object) -> bool:
	"""メッセージ送信の best-effort 版 (失敗時はログのみ残し False を返す)"""
	try:
		await channel.send(**kwargs)
	except _SEND_ERRORS as e:
		logger.warning("メッセージ送信失敗 (%s): %s", type(e).__name__, e)
		return False
	except Exception:
		logger.exception("メッセージ送信失敗")
		return False
	return True


async def safe_respond(ctx: discord.ApplicationContext, /, **kwargs: object) -> bool:
	"""インタラクション応答の best-effort 版 (失敗時はログのみ残し False を返す)"""
	try:
		await ctx.respond(**kwargs)
	except _SEND_ERRORS as e:
		logger.warning("インタラクション応答失敗 (%s): %s", type(e).__name__, e)
		return False
	except Exception:
		logger.exception("インタラクション応答失敗")
		return False
	return True
