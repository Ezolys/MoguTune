# Copyright (c) 2026 Milkeyyy

"""メンテナンスモード API"""

from __future__ import annotations

import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from mogutune_dashboard.access import CurrentUser
from mogutune_dashboard.deps import DbDep
from mogutune_dashboard.utils import to_jsonable

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])

STATE_ID = "maintenance"
MESSAGE_MAX_LENGTH = 1000


class MaintenanceUpdate(BaseModel):
	"""メンテナンスモードの更新リクエスト"""

	enabled: bool
	message: str | None = Field(default=None, max_length=MESSAGE_MAX_LENGTH)


@router.get("")
async def get_maintenance(db: DbDep) -> dict:
	"""現在のメンテナンス状態を返す"""
	doc = await db["bot_state"].find_one({"_id": STATE_ID})
	if doc is None:
		return {"enabled": False, "message": None, "updated_by": None, "updated_at": None}
	return to_jsonable({key: value for key, value in doc.items() if key != "_id"})


@router.put("")
async def update_maintenance(payload: MaintenanceUpdate, db: DbDep, user: CurrentUser) -> dict:
	"""メンテナンス状態を更新する (Bot はクイズ開始時にこの状態を確認する)"""
	message = payload.message.strip() if payload.message else None
	if message == "":
		message = None
	now = datetime.datetime.now(tz=datetime.UTC)
	updated_by = user.display_name
	await db["bot_state"].update_one(
		{"_id": STATE_ID},
		{"$set": {"enabled": payload.enabled, "message": message, "updated_by": updated_by, "updated_at": now}},
		upsert=True,
	)
	return {"enabled": payload.enabled, "message": message, "updated_by": updated_by, "updated_at": to_jsonable(now)}
