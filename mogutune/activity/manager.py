# Copyright (c) 2026 Milkeyyy

"""Activity セッションの管理 (guild_id → ActivitySession)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mogutune.activity.session import ActivitySession

if TYPE_CHECKING:
	from mogutune_core.activity_protocol import ServerMessage

	from mogutune.activity.bridge import ActivityBridge

logger = logging.getLogger(__name__)


class ActivitySessionManager:
	"""1 ギルド 1 Activity セッションの管理 (既存 QuizSession とは排他で運用する)"""

	def __init__(self) -> None:
		self.sessions: dict[int, ActivitySession] = {}
		self._instance_guild: dict[str, int] = {}
		self.bridge: ActivityBridge | None = None

	def attach(self, bridge: ActivityBridge) -> None:
		self.bridge = bridge

	def get(self, guild_id: int) -> ActivitySession | None:
		return self.sessions.get(guild_id)

	def guild_of(self, instance_id: str) -> int | None:
		return self._instance_guild.get(instance_id)

	def get_or_create(self, guild_id: int, channel_id: int, instance_id: str) -> ActivitySession:
		session = self.sessions.get(guild_id)
		if session is None:
			session = ActivitySession(guild_id, channel_id, instance_id, emit=self._emit)
			self.sessions[guild_id] = session
			logger.info("Activity セッション作成 (guild=%s instance=%s)", guild_id, instance_id)
		self._instance_guild[instance_id] = guild_id
		return session

	def forget(self, guild_id: int, instance_id: str) -> None:
		"""セッション破棄時の登録解除"""
		self.sessions.pop(guild_id, None)
		self._instance_guild.pop(instance_id, None)

	async def end_session(self, guild_id: int) -> None:
		session = self.sessions.pop(guild_id, None)
		if session is not None:
			await session.cancel()

	async def _emit(self, instance_id: str, message: ServerMessage, user_id: int | None = None) -> None:
		if self.bridge is not None:
			await self.bridge.send(instance_id, message, user_id)


activity_manager = ActivitySessionManager()
