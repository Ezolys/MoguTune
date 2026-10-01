# Copyright (c) 2026 Milkeyyy

"""コマンド実行ログ API"""

from __future__ import annotations

import re
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from mogutune_dashboard.config import get_settings
from mogutune_dashboard.deps import DbDep
from mogutune_dashboard.utils import daily_rows, date_string_expr, days_ago, fill_daily, recent_days, to_jsonable

router = APIRouter(prefix="/api/commands", tags=["commands"])

LOG_LIMIT = 200
FILTER_DAYS = 90
"""フィルター候補を集める対象期間 (日)"""


def _match(days: int, guild_id: int | None) -> dict:
	"""集計用の $match 条件を生成する"""
	match: dict = {"created_at": {"$gte": days_ago(days)}}
	if guild_id is not None:
		match["guild_id"] = guild_id
	return match


@router.get("/summary")
async def command_summary(
	db: DbDep,
	days: Annotated[int, Query(ge=1, le=90)] = 7,
	guild_id: Annotated[int | None, Query()] = None,
) -> dict:
	"""コマンド実行回数の集計 (合計・成功率・コマンド別・日別・サーバー別) を返す"""
	settings = get_settings()
	rows = (
		await db["command_logs"]
		.aggregate(
			[
				{"$match": _match(days, guild_id)},
				{
					"$facet": {
						"total": [{"$count": "count"}],
						"errors": [{"$match": {"ok": False}}, {"$count": "count"}],
						"by_command": [
							{
								"$group": {
									"_id": "$command",
									"count": {"$sum": 1},
									"errors": {"$sum": {"$cond": ["$ok", 0, 1]}},
								}
							},
							{"$sort": {"count": -1}},
							{"$limit": 10},
						],
						"by_day": [
							{
								"$group": {
									"_id": date_string_expr("created_at", settings.timezone),
									"count": {"$sum": 1},
									"errors": {"$sum": {"$cond": ["$ok", 0, 1]}},
								}
							},
							{"$sort": {"_id": 1}},
						],
						"by_guild": [
							{"$match": {"guild_id": {"$ne": None}}},
							{
								"$group": {
									"_id": "$guild_id",
									"guild_name": {"$last": "$guild_name"},
									"count": {"$sum": 1},
								}
							},
							{"$sort": {"count": -1}},
							{"$limit": 10},
						],
					}
				},
			]
		)
		.to_list(length=1)
	)
	facet = rows[0] if rows else {}
	total = _first_count(facet.get("total"))
	errors = _first_count(facet.get("errors"))
	success_rate = round((total - errors) / total * 100, 1) if total else 100.0

	days_list = recent_days(days, ZoneInfo(settings.timezone))
	return {
		"total": total,
		"errors": errors,
		"success_rate": success_rate,
		"by_command": [
			{"command": row["_id"], "count": row.get("count", 0), "errors": row.get("errors", 0)} for row in facet.get("by_command", [])
		],
		"by_day": fill_daily(daily_rows(facet.get("by_day", []), ("count", "errors")), days_list, ("count", "errors")),
		"by_guild": [
			{"guild_id": row["_id"], "guild_name": row.get("guild_name"), "count": row.get("count", 0)} for row in facet.get("by_guild", [])
		],
	}


@router.get("/logs")
async def command_logs(  # noqa: PLR0913, PLR0917
	db: DbDep,
	limit: Annotated[int, Query(ge=1, le=LOG_LIMIT)] = 50,
	offset: Annotated[int, Query(ge=0)] = 0,
	guild_id: Annotated[int | None, Query()] = None,
	command: Annotated[str | None, Query()] = None,
	ok: Annotated[bool | None, Query()] = None,
	query_text: Annotated[str | None, Query(alias="q")] = None,
) -> dict:
	"""コマンド実行ログの一覧を返す"""
	query: dict = {}
	if guild_id is not None:
		query["guild_id"] = guild_id
	if command:
		query["command"] = command
	if ok is not None:
		query["ok"] = ok
	if query_text:
		pattern = re.escape(query_text)
		query["$or"] = [
			{"guild_name": {"$regex": pattern, "$options": "i"}},
			{"command": {"$regex": pattern, "$options": "i"}},
			{"options": {"$regex": pattern, "$options": "i"}},
		]

	docs = await db["command_logs"].find(query).sort("created_at", -1).skip(offset).limit(limit).to_list(length=limit)
	total = await db["command_logs"].count_documents(query)
	return {"items": [to_jsonable({key: value for key, value in doc.items() if key != "_id"}) for doc in docs], "total": total}


@router.get("/filters")
async def command_filters(db: DbDep) -> dict:
	"""フィルター用のコマンド名一覧を返す"""
	names = await db["command_logs"].distinct("command", {"created_at": {"$gte": days_ago(FILTER_DAYS)}})
	return {"commands": sorted(name for name in names if isinstance(name, str))}


def _first_count(rows: list[dict] | None) -> int:
	"""$count 集計の先頭値を返す"""
	if not rows:
		return 0
	value = rows[0].get("count", 0)
	return int(value) if isinstance(value, (int, float)) else 0
