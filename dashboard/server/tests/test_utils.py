# Copyright (c) 2026 Milkeyyy

"""シリアライズと集計ヘルパーのテスト"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from bson import ObjectId

from mogutune_dashboard.utils import daily_rows, date_string_expr, days_ago, fill_daily, recent_days, to_jsonable


def test_to_jsonable() -> None:
	assert to_jsonable(datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)) == "2026-01-01T00:00:00+00:00"
	# naive は UTC とみなす
	assert to_jsonable(datetime.datetime(2026, 1, 1, 9)) == "2026-01-01T09:00:00+00:00"  # noqa: DTZ001
	assert to_jsonable(ObjectId("507f1f77bcf86cd799439011")) == "507f1f77bcf86cd799439011"
	assert to_jsonable({"a": [datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)]}) == {"a": ["2026-01-01T00:00:00+00:00"]}
	assert to_jsonable(1) == 1


def test_recent_days() -> None:
	now = datetime.datetime(2026, 1, 3, 12, tzinfo=datetime.UTC)
	assert recent_days(3, ZoneInfo("UTC"), now=now) == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_recent_days_with_timezone() -> None:
	# UTC 1月1日 0時は JST では 1月1日 9時
	now = datetime.datetime(2026, 1, 1, 0, tzinfo=datetime.UTC)
	assert recent_days(2, ZoneInfo("Asia/Tokyo"), now=now) == ["2025-12-31", "2026-01-01"]


def test_days_ago() -> None:
	now = datetime.datetime(2026, 1, 10, tzinfo=datetime.UTC)
	assert days_ago(3, now=now) == datetime.datetime(2026, 1, 7, tzinfo=datetime.UTC)


def test_date_string_expr() -> None:
	expr = date_string_expr("created_at", "UTC")
	assert expr["$dateToString"]["date"] == "$created_at"
	assert expr["$dateToString"]["format"] == "%Y-%m-%d"


def test_daily_rows_and_fill() -> None:
	rows = daily_rows([{"_id": "2026-01-02", "count": 5, "errors": 1}], ("count", "errors"))
	assert rows == [{"date": "2026-01-02", "count": 5, "errors": 1}]

	filled = fill_daily(rows, ["2026-01-01", "2026-01-02", "2026-01-03"], ("count", "errors"))
	assert filled == [
		{"date": "2026-01-01", "count": 0, "errors": 0},
		{"date": "2026-01-02", "count": 5, "errors": 1},
		{"date": "2026-01-03", "count": 0, "errors": 0},
	]
