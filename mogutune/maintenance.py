# Copyright (c) 2026 Milkeyyy

"""メンテナンスモードの状態管理 (ダッシュボードと MongoDB の bot_state コレクションで共有する)"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mogutune_core.db import DBManager

from mogutune.telemetry import utcnow

if TYPE_CHECKING:
	import pymongo.asynchronous.collection

logger = logging.getLogger(__name__)

STATE_ID = "maintenance"
"""bot_state コレクションのメンテナンスドキュメントID"""


def _collection() -> pymongo.asynchronous.collection.AsyncCollection:
	"""bot_state コレクションを取得する"""
	return DBManager.db.get_collection("bot_state")


def _default_state() -> dict[str, Any]:
	"""メンテナンス状態のデフォルト値 (無効) を返す"""
	return {"enabled": False, "message": None, "updated_by": None, "updated_at": None}


async def fetch_state() -> dict[str, Any]:
	"""メンテナンス状態を取得する (取得失敗時は無効として扱う)"""
	try:
		doc = await _collection().find_one({"_id": STATE_ID})
	except Exception:
		logger.exception("メンテナンス状態の取得に失敗")
		return _default_state()
	if not isinstance(doc, dict):
		return _default_state()
	return {
		"enabled": bool(doc.get("enabled", False)),
		"message": doc.get("message"),
		"updated_by": doc.get("updated_by"),
		"updated_at": doc.get("updated_at"),
	}


async def is_enabled() -> bool:
	"""メンテナンスモードが有効かどうかを返す"""
	return bool((await fetch_state())["enabled"])


async def set_state(*, enabled: bool, updated_by: str, message: str | None = None) -> None:
	"""メンテナンス状態を更新する (失敗時は例外を送出する)"""
	await _collection().update_one(
		{"_id": STATE_ID},
		{"$set": {"enabled": enabled, "message": message, "updated_by": updated_by, "updated_at": utcnow()}},
		upsert=True,
	)
	logger.info("メンテナンスモードを更新: %s (実行者: %s)", enabled, updated_by)
