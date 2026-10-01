# Copyright (c) 2026 Milkeyyy

"""集計エンドポイントの回帰テスト (pymongo async の aggregate 呼び出し検証)"""

from __future__ import annotations

import datetime

import pytest

from mogutune_dashboard.config import Settings
from mogutune_dashboard.routers import commands, errors, quiz


class FakeCursor:
	"""AsyncCommandCursor の最小スタブ"""

	def __init__(self, rows: list[dict]) -> None:
		self._rows = rows

	async def to_list(self, length: int | None = None) -> list[dict]:
		return self._rows[:length] if length is not None else list(self._rows)


class FakeCollection:
	"""AsyncCollection の最小スタブ (aggregate のみ実装)"""

	def __init__(self, rows: list[dict]) -> None:
		self.rows = rows
		self.pipelines: list[list[dict]] = []

	async def aggregate(self, pipeline: list[dict]) -> FakeCursor:
		# await せずに使うと AttributeError になるため、テストで呼び出し方を検証する
		self.pipelines.append(pipeline)
		return FakeCursor(self.rows)


class FakeDb:
	"""AsyncDatabase の最小スタブ"""

	def __init__(self, collections: dict[str, FakeCollection]) -> None:
		self.collections = collections

	def __getitem__(self, name: str) -> FakeCollection:
		return self.collections[name]


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
	"""集計 API が参照する設定を固定する"""
	value = Settings(
		db_uri="mongodb://localhost:27017",
		db_name="mogutune",
		cf_access_team_domain="",
		cf_access_aud="",
		allowed_emails=frozenset(),
		auth_disabled=True,
		timezone="UTC",
		static_dir=".",
		allowed_origins=frozenset(),
	)
	monkeypatch.setattr(commands, "get_settings", lambda: value)
	monkeypatch.setattr(quiz, "get_settings", lambda: value)
	monkeypatch.setattr(errors, "get_settings", lambda: value)
	return value


async def test_command_summary_aggregates() -> None:
	facet = {
		"total": [{"count": 10}],
		"errors": [{"count": 2}],
		"by_command": [{"_id": "play", "count": 8, "errors": 1}],
		"by_day": [{"_id": "2026-01-01", "count": 10, "errors": 2}],
		"by_guild": [{"_id": 1, "guild_name": "test", "count": 10}],
	}
	collection = FakeCollection([facet])
	result = await commands.command_summary(db=FakeDb({"command_logs": collection}), days=7, guild_id=None)

	assert result["total"] == 10
	assert result["errors"] == 2
	assert result["success_rate"] == 80.0
	assert result["by_command"] == [{"command": "play", "count": 8, "errors": 1}]
	assert result["by_guild"] == [{"guild_id": 1, "guild_name": "test", "count": 10}]
	assert len(result["by_day"]) == 7
	# $match が期間指定つきで組み立てられていること
	assert collection.pipelines[0][0]["$match"]["created_at"]["$gte"] is not None


async def test_quiz_summary_aggregates() -> None:
	facet = {
		"total": [{"count": 5}],
		"completed": [{"count": 4}],
		"participants": [{"count": 12}],
		"by_day": [{"_id": "2026-01-01", "count": 5, "participants": 12}],
	}
	collection = FakeCollection([facet])
	result = await quiz.quiz_summary(db=FakeDb({"quiz_history": collection}), days=30, guild_id=None)

	assert result["total"] == 5
	assert result["completed"] == 4
	assert result["participants"] == 12
	assert len(result["by_day"]) == 30


async def test_error_summary_aggregates() -> None:
	facet = {
		"total": [{"count": 3}],
		"last_24h": [{"count": 1}],
		"by_day": [{"_id": "2026-01-01", "count": 3}],
		"by_source": [{"_id": "QuizCommands.play", "count": 2}],
		"signatures": [
			{
				"_id": "hash",
				"count": 2,
				"source": "QuizCommands.play",
				"description": "desc",
				"error_code": "01900000-0000-7000-8000-000000000001",
				"last_seen": datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
			}
		],
	}
	collection = FakeCollection([facet])
	result = await errors.error_summary(db=FakeDb({"internal_errors": collection}), days=30)

	assert result["total"] == 3
	assert result["last_24h"] == 1
	assert result["by_source"] == [{"source": "QuizCommands.play", "count": 2}]
	assert result["signatures"][0]["last_seen"] == "2026-01-01T00:00:00+00:00"
	assert len(result["by_day"]) == 30
