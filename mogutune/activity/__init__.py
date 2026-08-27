# Copyright (c) 2026 Milkeyyy

"""Activity (Discord アクティビティ) 用のブリッジとクイズセッション"""

from __future__ import annotations

import logging
from os import getenv
from typing import TYPE_CHECKING

import mafic

from mogutune.activity.bridge import ActivityBridge
from mogutune.activity.manager import activity_manager

if TYPE_CHECKING:
	import discord

logger = logging.getLogger(__name__)


async def _on_track_end(event: mafic.TrackEndEvent) -> None:
	session = activity_manager.get(event.player.guild.id)
	if session is None:
		return
	if event.reason == mafic.EndReason.FINISHED:
		session.on_track_finished(event.track)


async def _on_track_exception(event: mafic.TrackExceptionEvent) -> None:
	session = activity_manager.get(event.player.guild.id)
	if session is None:
		return
	session.on_track_exception(event.track)


def setup_activity(bot: discord.Client) -> None:
	"""Activity ブリッジと mafic イベントリスナーを登録する (on_ready から呼ぶ)

	ブリッジは一度だけ起動する (接続済みなら何もしない)。
	"""
	if activity_manager.bridge is not None:
		return
	secret = getenv("ACTIVITY_BRIDGE_SECRET", "")
	if not secret:
		logger.warning("ACTIVITY_BRIDGE_SECRET が未設定のため Activity ブリッジを起動しません")
		return

	bot.add_listener(_on_track_end, "on_track_end")
	bot.add_listener(_on_track_exception, "on_track_exception")

	bridge = ActivityBridge(activity_manager, secret, port=int(getenv("ACTIVITY_BRIDGE_PORT", "8765")))
	activity_manager.attach(bridge)
	bot.loop.create_task(bridge.start())
	logger.info("Activity ブリッジを起動します")
