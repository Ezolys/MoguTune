# Copyright (c) 2026 Milkeyyy

import logging
import traceback

import discord
import uuid_utils as uuid

from mogutune import telemetry
from mogutune.embeds import EmbedsTemplates

logger = logging.getLogger(__name__)


class DebugLogger:
	debug_guild: discord.Guild | None = None
	debug_channel: discord.TextChannel | None = None

	@classmethod
	async def log(cls, text: str) -> None:
		"""デバッグログを送信する"""
		if cls.debug_guild is None or cls.debug_channel is None:
			logger.warning("デバッグログ記録中止 - デバッグ用サーバーまたはチャンネルが設定されていません")
			return
		try:
			await cls.debug_channel.send(text)
		except Exception:
			logger.error("デバッグログ送信失敗")
			logger.error(traceback.format_exc())

	@classmethod
	async def report_internal_error(
		cls,
		traceback_text: str,
		description: str = "",
		*,
		source: str = "",
		guild_id: int | None = None,
		user_id: int | None = None,
		command: str | None = None,
	) -> str:
		"""内部エラーを報告してエラーコードを返す

		ダッシュボード向けにDBへ記録し、デバッグチャンネルが設定されていればDiscordへも通知する。
		記録・通知に失敗してもエラーコードは返す。
		"""
		error_code = str(uuid.uuid7())

		# ダッシュボード用にDBへ記録する (失敗してもDiscord通知は続行する)
		await telemetry.record_error(
			error_code,
			telemetry.ErrorRecord(
				source=source,
				description=description,
				traceback_text=traceback_text,
				guild_id=guild_id,
				user_id=user_id,
				command=command,
			),
		)

		if cls.debug_guild is None or cls.debug_channel is None:
			logger.warning("内部エラーのDiscord通知をスキップ - デバッグ用サーバーまたはチャンネルが設定されていません")
			return error_code

		try:
			desc_section = f"\n概要\n```{description}```" if description else ""
			await cls.debug_channel.send(
				embed=EmbedsTemplates.internal_error(
					description=f"エラーコード\n```{error_code}```{desc_section}\nトレースバック\n```{traceback_text}```"
				)
			)
		except Exception:
			logger.error("内部エラー報告失敗")
			logger.error(traceback.format_exc())
		return error_code
