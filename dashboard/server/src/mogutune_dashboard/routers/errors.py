# Copyright (c) 2026 Milkeyyy

"""内部エラー API"""

from __future__ import annotations

import re
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from mogutune_dashboard.config import get_settings
from mogutune_dashboard.deps import DbDep
from mogutune_dashboard.utils import daily_rows, date_string_expr, days_ago, fill_daily, recent_days, to_jsonable

router = APIRouter(prefix="/api/errors", tags=["errors"])

ERROR_LIMIT = 200
SIGNATURE_LIMIT = 20


@router.get("/summary")
async def error_summary(
	db: DbDep,
	days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> dict:
	"""内部エラーの発生数 (合計・直近24時間・日別・発生元別・シグネチャ別) を返す"""
	settings = get_settings()
	cursor = await db["internal_errors"].aggregate(
		[
			{"$match": {"created_at": {"$gte": days_ago(days)}}},
			{
				"$facet": {
					"total": [{"$count": "count"}],
					"last_24h": [{"$match": {"created_at": {"$gte": days_ago(1)}}}, {"$count": "count"}],
					"by_day": [
						{"$group": {"_id": date_string_expr("created_at", settings.timezone), "count": {"$sum": 1}}},
						{"$sort": {"_id": 1}},
					],
					"by_source": [
						{"$group": {"_id": "$source", "count": {"$sum": 1}}},
						{"$sort": {"count": -1}},
						{"$limit": 10},
					],
					"signatures": [
						{
							"$group": {
								"_id": "$traceback_hash",
								"count": {"$sum": 1},
								"source": {"$last": "$source"},
								"description": {"$last": "$description"},
								"error_code": {"$last": "$_id"},
								"last_seen": {"$max": "$created_at"},
							}
						},
						{"$sort": {"last_seen": -1}},
						{"$limit": SIGNATURE_LIMIT},
					],
				}
			},
		]
	)
	rows = await cursor.to_list(length=1)
	facet = rows[0] if rows else {}
	days_list = recent_days(days, ZoneInfo(settings.timezone))
	return {
		"total": _first_count(facet.get("total")),
		"last_24h": _first_count(facet.get("last_24h")),
		"by_day": fill_daily(daily_rows(facet.get("by_day", [])), days_list),
		"by_source": [{"source": row["_id"] or "(unknown)", "count": row.get("count", 0)} for row in facet.get("by_source", [])],
		"signatures": [to_jsonable(row) for row in facet.get("signatures", [])],
	}


@router.get("")
async def list_errors(
	db: DbDep,
	limit: Annotated[int, Query(ge=1, le=ERROR_LIMIT)] = 50,
	offset: Annotated[int, Query(ge=0)] = 0,
	source: Annotated[str | None, Query()] = None,
	query_text: Annotated[str | None, Query(alias="q")] = None,
) -> dict:
	"""内部エラーの一覧を返す (トレースバックは含まない)"""
	query: dict = {}
	if source:
		query["source"] = source
	if query_text:
		pattern = re.escape(query_text)
		query["$or"] = [
			{"description": {"$regex": pattern, "$options": "i"}},
			{"source": {"$regex": pattern, "$options": "i"}},
			{"command": {"$regex": pattern, "$options": "i"}},
			{"_id": query_text},
		]

	docs = await db["internal_errors"].find(query, {"traceback": 0}).sort("created_at", -1).skip(offset).limit(limit).to_list(length=limit)
	total = await db["internal_errors"].count_documents(query)
	return {"items": [_error_item(doc) for doc in docs], "total": total}


def _error_item(doc: dict) -> dict:
	"""エラードキュメントを API レスポンス用の形式へ変換する"""
	return to_jsonable({key: value for key, value in doc.items() if key != "_id"} | {"error_code": doc["_id"]})


@router.get("/{error_code}")
async def error_detail(error_code: str, db: DbDep) -> dict:
	"""エラーコードに対応する内部エラーの詳細 (トレースバック含む) を返す"""
	doc = await db["internal_errors"].find_one({"_id": error_code})
	if doc is None:
		raise HTTPException(status_code=404, detail="エラーが見つかりません")
	return to_jsonable({key: value for key, value in doc.items() if key != "_id"} | {"error_code": doc["_id"]})


def _first_count(rows: list[dict] | None) -> int:
	"""$count 集計の先頭値を返す"""
	if not rows:
		return 0
	value = rows[0].get("count", 0)
	return int(value) if isinstance(value, (int, float)) else 0
