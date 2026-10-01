# Copyright (c) 2026 Milkeyyy

"""Bot の稼働状況 API"""

from __future__ import annotations

import datetime

from fastapi import APIRouter

from mogutune_dashboard.deps import DbDep
from mogutune_dashboard.utils import to_jsonable

router = APIRouter(prefix="/api", tags=["status"])

ONLINE_THRESHOLD_SECONDS = 90.0
"""ハートビートがこの秒数以内ならオンラインとみなす"""


@router.get("/status")
async def get_status(db: DbDep) -> dict:
	"""Bot の稼働状況 (ハートビート) を返す"""
	doc = await db["bot_status"].find_one({"_id": "current"})
	if doc is None:
		return {"online": False, "status": None}

	updated_at = doc.get("updated_at")
	online = False
	if isinstance(updated_at, datetime.datetime):
		if updated_at.tzinfo is None:
			updated_at = updated_at.replace(tzinfo=datetime.UTC)
		online = (datetime.datetime.now(tz=datetime.UTC) - updated_at).total_seconds() <= ONLINE_THRESHOLD_SECONDS

	status = {key: value for key, value in doc.items() if key != "_id"}
	return {"online": online, "status": to_jsonable(status)}
