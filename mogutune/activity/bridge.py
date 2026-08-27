# Copyright (c) 2026 Milkeyyy

"""Activity サーバーとのブリッジ (WS サーバー・共有シークレット認証)

Activity サーバーからの接続を 1 本受け、クイズのイベントを中継する。
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING

from mogutune_core.activity_protocol import (
	BridgePongMessage,
	ServerRelayMessage,
	bridge_to_bot_adapter,
)
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

if TYPE_CHECKING:
	from mogutune_core.activity_protocol import BridgeToBotMessage, ServerMessage

	from mogutune.activity.manager import ActivitySessionManager

logger = logging.getLogger(__name__)


class ActivityBridge:
	"""Activity サーバーとの WS ブリッジ"""

	def __init__(
		self,
		manager: ActivitySessionManager,
		secret: str,
		host: str = "0.0.0.0",  # noqa: S104 (内部ネットワークの専用ブリッジ)
		port: int = 8765,
	) -> None:
		self.manager = manager
		self.secret = secret
		self.host = host
		self.port = port
		self._ws: ServerConnection | None = None
		self._server: Server | None = None
		self._send_lock = asyncio.Lock()

	async def start(self) -> None:
		self._server = await serve(self._handle, self.host, self.port)
		logger.info("Activity ブリッジ開始: %s:%d", self.host, self.port)

	async def stop(self) -> None:
		if self._server is not None:
			self._server.close()
			await self._server.wait_closed()
		if self._ws is not None:
			await self._ws.close()

	async def send(self, instance_id: str, message: ServerMessage, user_id: int | None = None) -> None:
		"""セッションからの配信 (接続が無ければ破棄)"""
		ws = self._ws
		if ws is None:
			return
		relay = ServerRelayMessage(type="message", instance_id=instance_id, user_id=user_id, message=message)
		async with self._send_lock:
			try:
				await ws.send(relay.model_dump_json())
			except Exception:
				logger.warning("ブリッジ送信に失敗 (instance_id=%s)", instance_id)

	async def _handle(self, websocket: ServerConnection) -> None:
		if websocket.request.headers.get("Authorization", "") != f"Bearer {self.secret}":
			await websocket.close(code=4401)
			return
		if self._ws is not None:
			await websocket.close(code=4400)
			return
		self._ws = websocket
		logger.info("Activity ブリッジ接続")
		try:
			async for raw in websocket:
				try:
					message = bridge_to_bot_adapter.validate_json(raw)
				except Exception:
					logger.debug("不正なブリッジメッセージ: %s", raw[:200])
					continue
				await self._dispatch(message)
		except ConnectionClosed:
			pass
		finally:
			self._ws = None
			logger.info("Activity ブリッジ切断")

	async def _dispatch(self, message: BridgeToBotMessage) -> None:
		if message.type == "ping":
			await self._send_pong(message.instance_id, message.t)
			return
		if message.type == "join":
			session = self.manager.get_or_create(message.guild_id, message.channel_id, message.instance_id)
			session.instance_id = message.instance_id
			await session.join(message.user)
			session.start()
			return
		guild_id = self.manager.guild_of(message.instance_id)
		if guild_id is None:
			logger.debug("不明な instance_id: %s", message.instance_id)
			return
		session = self.manager.get(guild_id)
		if session is None:
			return
		if message.type == "leave":
			await session.leave(message.user_id)
		elif message.type == "state_request":
			await session.request_state()
		elif message.type == "client":
			session.handle(message.user_id, message.message)

	async def _send_pong(self, instance_id: str, t: float) -> None:
		ws = self._ws
		if ws is None:
			return
		pong = BridgePongMessage(type="pong", instance_id=instance_id, t=t, server_time=time.time() * 1000)
		async with self._send_lock:
			with suppress(Exception):
				await ws.send(pong.model_dump_json())
