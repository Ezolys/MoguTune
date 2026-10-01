# Copyright (c) 2026 Milkeyyy

"""クイズの実行状況 API"""

from __future__ import annotations

from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from mogutune_dashboard.config import get_settings
from mogutune_dashboard.deps import DbDep
from mogutune_dashboard.utils import daily_rows, date_string_expr, days_ago, fill_daily, recent_days, to_jsonable

router = APIRouter(prefix="/api/quiz", tags=["quiz"])

HISTORY_LIMIT = 200


@router.get("/active")
async def active_quizzes(db: DbDep) -> dict:
	"""現在実行中のクイズセッションを返す (Bot のハートビートから取得)"""
	doc = await db["bot_status"].find_one({"_id": "current"}, {"active_sessions": 1, "updated_at": 1})
	if doc is None:
		return {"sessions": [], "updated_at": None}
	return {
		"sessions": to_jsonable(doc.get("active_sessions", [])),
		"updated_at": to_jsonable(doc.get("updated_at")),
	}


@router.get("/history")
async def quiz_history(
	db: DbDep,
	limit: Annotated[int, Query(ge=1, le=HISTORY_LIMIT)] = 50,
	offset: Annotated[int, Query(ge=0)] = 0,
	guild_id: Annotated[int | None, Query()] = None,
) -> dict:
	"""終了したクイズの履歴を返す"""
	query: dict = {}
	if guild_id is not None:
		query["guild_id"] = guild_id

	docs = await db["quiz_history"].find(query).sort("ended_at", -1).skip(offset).limit(limit).to_list(length=limit)
	total = await db["quiz_history"].count_documents(query)
	return {"items": [to_jsonable({key: value for key, value in doc.items() if key != "_id"}) for doc in docs], "total": total}


@router.get("/summary")
async def quiz_summary(
	db: DbDep,
	days: Annotated[int, Query(ge=1, le=90)] = 30,
	guild_id: Annotated[int | None, Query()] = None,
) -> dict:
	"""クイズ実施回数の集計 (合計・完走数・参加者数・日別) を返す"""
	settings = get_settings()
	match: dict = {"ended_at": {"$gte": days_ago(days)}}
	if guild_id is not None:
		match["guild_id"] = guild_id

	cursor = await db["quiz_history"].aggregate(
		[
			{"$match": match},
			{
				"$facet": {
					"total": [{"$count": "count"}],
					"completed": [{"$match": {"$expr": {"$gte": ["$completed_questions", "$question_total"]}}}, {"$count": "count"}],
					"participants": [{"$group": {"_id": None, "count": {"$sum": {"$size": "$participants"}}}}],
					"by_day": [
						{
							"$group": {
								"_id": date_string_expr("ended_at", settings.timezone),
								"count": {"$sum": 1},
								"participants": {"$sum": {"$size": "$participants"}},
							}
						},
						{"$sort": {"_id": 1}},
					],
				}
			},
		]
	)
	rows = await cursor.to_list(length=1)
	facet = rows[0] if rows else {}
	total = _first_count(facet.get("total"))
	days_list = recent_days(days, ZoneInfo(settings.timezone))
	return {
		"total": total,
		"completed": _first_count(facet.get("completed")),
		"participants": _first_count(facet.get("participants")),
		"by_day": fill_daily(daily_rows(facet.get("by_day", []), ("count", "participants")), days_list, ("count", "participants")),
	}


def _first_count(rows: list[dict] | None) -> int:
	"""$count / $group 集計の先頭値を返す"""
	if not rows:
		return 0
	value = rows[0].get("count", 0)
	return int(value) if isinstance(value, (int, float)) else 0
