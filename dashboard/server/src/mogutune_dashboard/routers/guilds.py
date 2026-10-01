# Copyright (c) 2026 Milkeyyy

"""サーバー一覧 API"""

from __future__ import annotations

from fastapi import APIRouter

from mogutune_dashboard.deps import DbDep
from mogutune_dashboard.utils import to_jsonable

router = APIRouter(prefix="/api", tags=["guilds"])

GUILD_LIMIT = 1000


@router.get("/guilds")
async def list_guilds(db: DbDep) -> list[dict]:
	"""Bot が参加しているサーバー一覧を返す"""
	docs = await db["guilds"].find({}).sort([("member_count", -1), ("name", 1)]).to_list(length=GUILD_LIMIT)
	return [to_jsonable({"guild_id": doc["_id"], **{key: value for key, value in doc.items() if key != "_id"}}) for doc in docs]
