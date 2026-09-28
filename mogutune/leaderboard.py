# Copyright (c) 2026 Milkeyyy

"""クイズ結果の累計統計 (リーダーボード) の集計・DBアクセス"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mogutune_core.db import DBManager
from pymongo import UpdateOne

if TYPE_CHECKING:
	import datetime
	from collections.abc import Mapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuizStats:
	"""1回のクイズ終了時にプレイヤーへ加算する値"""

	user_id: int
	"""プレイヤーのID"""
	correct: int
	"""正解数"""
	questions: int
	"""出題された問題数"""


@dataclass(frozen=True)
class LeaderboardEntry:
	"""リーダーボードの1行"""

	user_id: int
	"""プレイヤーのID"""
	correct: int
	"""累計正解数"""
	questions: int
	"""累計参加問題数"""
	quizzes: int
	"""累計参加クイズ数"""

	@classmethod
	def from_doc(cls, doc: object) -> LeaderboardEntry | None:
		"""Mongo ドキュメントから生成 (user_id が欠損・型不一致の場合は None、他の数値は不正値を0へ)"""
		if not isinstance(doc, dict):
			return None
		user_id = doc.get("user_id")
		if not isinstance(user_id, int):
			return None

		def _int(key: str) -> int:
			value = doc.get(key)
			return value if isinstance(value, int) and value >= 0 else 0

		return cls(user_id=user_id, correct=_int("correct"), questions=_int("questions"), quizzes=_int("quizzes"))


def build_quiz_stats(q_results: dict[int, int | None], question_counts: Mapping[int, int]) -> list[QuizStats]:
	"""問題別結果とプレイヤーごとの参加問題数から加算値を生成する"""
	correct_counts: dict[int, int] = {}
	for player_id in q_results.values():
		if player_id is not None:
			correct_counts[player_id] = correct_counts.get(player_id, 0) + 1
	user_ids = set(question_counts) | set(correct_counts)
	return [
		QuizStats(
			user_id=user_id,
			correct=correct_counts.get(user_id, 0),
			questions=question_counts.get(user_id, 0),
		)
		for user_id in sorted(user_ids)
	]


def accuracy_percent(correct: int, questions: int) -> float:
	"""正解率 (%) を返す (問題数0の場合は0.0)"""
	if questions <= 0:
		return 0.0
	return correct / questions * 100


async def record_quiz_results(guild_id: int, stats: list[QuizStats], now: datetime.datetime) -> None:
	"""クイズ結果を leaderboard コレクションへ加算する"""
	if not stats:
		return
	operations = [
		UpdateOne(
			{"_id": f"{guild_id}:{s.user_id}", "guild_id": guild_id, "user_id": s.user_id},
			{
				"$inc": {"correct": s.correct, "questions": s.questions, "quizzes": 1},
				"$set": {"updated_at": now},
				"$setOnInsert": {"created_at": now},
			},
			upsert=True,
		)
		for s in stats
	]
	logger.debug("リーダーボードへ記録: %d (%d人)", guild_id, len(stats))
	await DBManager.col_leaderboard.bulk_write(operations)


async def fetch_top(guild_id: int, limit: int) -> list[LeaderboardEntry]:
	"""ギルドの上位エントリを取得する (正解数降順・同数はID昇順)"""
	docs = (
		await DBManager.col_leaderboard.find({"guild_id": guild_id})
		.sort([("correct", -1), ("user_id", 1)])
		.limit(limit)
		.to_list(length=limit)
	)
	return [entry for entry in (LeaderboardEntry.from_doc(doc) for doc in docs) if entry is not None]


async def fetch_rank(guild_id: int, user_id: int) -> tuple[int, LeaderboardEntry | None]:
	"""ユーザーの順位 (1始まり・同点同順) と自分のエントリを返す (記録がない場合は (0, None))"""
	doc = await DBManager.col_leaderboard.find_one({"_id": f"{guild_id}:{user_id}"})
	entry = LeaderboardEntry.from_doc(doc)
	if entry is None:
		return 0, None
	higher = await DBManager.col_leaderboard.count_documents({"guild_id": guild_id, "correct": {"$gt": entry.correct}})
	return higher + 1, entry


if __name__ == "__main__":
	# 純粋ロジックの自己チェック
	assert accuracy_percent(0, 0) == 0.0  # noqa: S101
	assert accuracy_percent(3, 4) == 75.0  # noqa: S101, PLR2004
	assert LeaderboardEntry.from_doc(None) is None  # noqa: S101
	assert LeaderboardEntry.from_doc({"user_id": "x"}) is None  # noqa: S101
	assert LeaderboardEntry.from_doc({"user_id": 1, "correct": -1}) == LeaderboardEntry(1, 0, 0, 0)  # noqa: S101
	# 正解者は参加問題数に含まれ、途中退出者 (question_counts のみ) も加算される
	_stats = build_quiz_stats({1: 10, 2: None, 3: 10}, {10: 3, 20: 2})
	assert _stats == [QuizStats(10, 2, 3), QuizStats(20, 0, 2)]  # noqa: S101
	# 正解者が question_counts に無い場合も questions は 0 として記録する
	assert build_quiz_stats({5: 99}, {}) == [QuizStats(99, 1, 0)]  # noqa: S101
	assert build_quiz_stats({}, {}) == []  # noqa: S101
	print("leaderboard self-check passed")  # noqa: T201
