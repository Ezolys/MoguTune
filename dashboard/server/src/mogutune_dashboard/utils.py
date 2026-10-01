# Copyright (c) 2026 Milkeyyy

"""API レスポンス向けのシリアライズと集計用ヘルパー"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from bson import ObjectId

if TYPE_CHECKING:
	from collections.abc import Iterable, Mapping, Sequence
	from zoneinfo import ZoneInfo


def to_jsonable(value: Any) -> Any:  # noqa: ANN401
	"""MongoDB の値を JSON 化できる値へ変換する"""
	if isinstance(value, datetime.datetime):
		if value.tzinfo is None:
			value = value.replace(tzinfo=datetime.UTC)
		return value.astimezone(datetime.UTC).isoformat()
	if isinstance(value, ObjectId):
		return str(value)
	if isinstance(value, dict):
		return {str(key): to_jsonable(item) for key, item in value.items()}
	if isinstance(value, (list, tuple)):
		return [to_jsonable(item) for item in value]
	return value


def days_ago(days: int, now: datetime.datetime | None = None) -> datetime.datetime:
	"""指定日数前の時刻 (UTC) を返す"""
	return (now or datetime.datetime.now(tz=datetime.UTC)) - datetime.timedelta(days=days)


def recent_days(days: int, tz: ZoneInfo, now: datetime.datetime | None = None) -> list[str]:
	"""直近 days 日分の日付 (YYYY-MM-DD) を古い順で返す"""
	current = (now or datetime.datetime.now(tz=datetime.UTC)).astimezone(tz)
	return [(current.date() - datetime.timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]


def date_string_expr(field: str, tz: str) -> dict:
	"""$dateToString で日付文字列へ変換する集計式を返す"""
	return {"$dateToString": {"format": "%Y-%m-%d", "date": f"${field}", "timezone": tz}}


def daily_rows(rows: Iterable[Mapping[str, Any]], keys: Sequence[str] = ("count",)) -> list[dict]:
	"""$dateToString の集計結果 (_id に日付) を date キーを持つ行へ正規化する"""
	return [{"date": row["_id"], **{key: row.get(key, 0) for key in keys}} for row in rows]


def fill_daily(rows: Iterable[Mapping[str, Any]], days: Sequence[str], keys: Sequence[str] = ("count",)) -> list[dict]:
	"""集計結果に存在しない日付を 0 で埋めて日付順に揃える"""
	by_day = {row["date"]: row for row in rows}
	filled: list[dict] = []
	for day in days:
		row = by_day.get(day)
		filled.append({"date": day, **{key: int(row.get(key, 0)) if row else 0 for key in keys}})
	return filled
