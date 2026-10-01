# Copyright (c) 2026 Milkeyyy

"""ダッシュボード向けのテレメトリ (コマンド実行・内部エラー・稼働状況・サーバー一覧・クイズ履歴) の記録"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import logging
import re
from typing import TYPE_CHECKING

from mogutune_core.db import DBManager
from pymongo import UpdateOne

if TYPE_CHECKING:
	from collections.abc import Iterable

	import pymongo.asynchronous.collection

logger = logging.getLogger(__name__)

SECONDS_PER_DAY = 60 * 60 * 24
COMMAND_LOG_TTL_DAYS = 90
"""コマンド実行ログを保持する日数"""
ERROR_LOG_TTL_DAYS = 180
"""内部エラーを保持する日数"""
BOT_STATUS_ID = "current"
"""稼働状況ドキュメントのID"""

# repr に含まれるメモリアドレスを除去して同一エラーを同じハッシュに寄せる
_ADDRESS_PATTERN = re.compile(r"0x[0-9a-fA-F]+")


def utcnow() -> datetime.datetime:
	"""現在時刻 (UTC, tz-aware) を返す"""
	return datetime.datetime.now(tz=datetime.UTC)


def _collection(name: str) -> pymongo.asynchronous.collection.AsyncCollection:
	"""テレメトリ用コレクションを取得する"""
	return DBManager.db.get_collection(name)


def _traceback_hash(traceback_text: str) -> str:
	"""トレースバックを正規化したハッシュを返す (同一エラーの集計用)"""
	normalized = _ADDRESS_PATTERN.sub("0xADDR", traceback_text)
	return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


@dataclasses.dataclass
class CommandRecord:
	"""コマンド実行ログの1件"""

	command: str
	ok: bool = True
	guild_id: int | None = None
	guild_name: str | None = None
	channel_id: int | None = None
	user_id: int | None = None
	options: list[str] = dataclasses.field(default_factory=list)
	error_type: str | None = None
	error_code: str | None = None


@dataclasses.dataclass
class ErrorRecord:
	"""内部エラーの1件"""

	source: str = ""
	description: str = ""
	traceback_text: str = ""
	guild_id: int | None = None
	user_id: int | None = None
	command: str | None = None


@dataclasses.dataclass
class QuizHistory:
	"""クイズ1回分の履歴"""

	guild_id: int
	query: str
	question_total: int
	completed_questions: int
	participants: list[int]
	correct_counts: dict[int, int]
	ended_at: datetime.datetime
	guild_name: str | None = None
	channel_id: int | None = None
	voice_channel_name: str | None = None
	owner_id: int | None = None
	started_at: datetime.datetime | None = None


@dataclasses.dataclass(frozen=True)
class GuildInfo:
	"""ダッシュボード表示用のサーバー情報"""

	id: int
	name: str
	member_count: int
	icon_url: str | None = None
	joined_at: datetime.datetime | None = None


async def ensure_indexes() -> None:
	"""テレメトリ用コレクションのインデックスを作成する (失敗しても起動処理は継続させる)"""
	try:
		col_commands = _collection("command_logs")
		await col_commands.create_index("created_at", expireAfterSeconds=COMMAND_LOG_TTL_DAYS * SECONDS_PER_DAY)
		await col_commands.create_index([("guild_id", 1), ("created_at", -1)])
		await col_commands.create_index([("command", 1), ("created_at", -1)])

		col_errors = _collection("internal_errors")
		await col_errors.create_index("created_at", expireAfterSeconds=ERROR_LOG_TTL_DAYS * SECONDS_PER_DAY)
		await col_errors.create_index([("traceback_hash", 1), ("created_at", -1)])
		await col_errors.create_index([("source", 1), ("created_at", -1)])

		await _collection("quiz_history").create_index([("guild_id", 1), ("ended_at", -1)])
	except Exception:
		logger.exception("テレメトリのインデックス作成に失敗")


async def record_command(record: CommandRecord) -> None:
	"""コマンド実行ログを記録する (失敗しても呼び出し元の処理は継続させる)"""
	try:
		await _collection("command_logs").insert_one(
			{
				"command": record.command,
				"ok": record.ok,
				"guild_id": record.guild_id,
				"guild_name": record.guild_name,
				"channel_id": record.channel_id,
				"user_id": record.user_id,
				"options": record.options,
				"error_type": record.error_type,
				"error_code": record.error_code,
				"created_at": utcnow(),
			}
		)
	except Exception:
		logger.exception("コマンド実行ログの記録に失敗")


async def record_error(error_code: str, record: ErrorRecord) -> None:
	"""内部エラーを記録する (失敗しても呼び出し元の処理は継続させる)"""
	try:
		await _collection("internal_errors").insert_one(
			{
				"_id": error_code,
				"source": record.source,
				"description": record.description,
				"traceback": record.traceback_text,
				"traceback_hash": _traceback_hash(record.traceback_text),
				"guild_id": record.guild_id,
				"user_id": record.user_id,
				"command": record.command,
				"created_at": utcnow(),
			}
		)
	except Exception:
		logger.exception("内部エラーの記録に失敗")


async def update_bot_status(status: dict) -> None:
	"""稼働状況のスナップショットを保存する (失敗しても呼び出し元の処理は継続させる)"""
	try:
		now = utcnow()
		await _collection("bot_status").update_one(
			{"_id": BOT_STATUS_ID},
			{"$set": {**status, "updated_at": now}, "$setOnInsert": {"created_at": now}},
			upsert=True,
		)
	except Exception:
		logger.exception("稼働状況の記録に失敗")


def _guild_update(info: GuildInfo, now: datetime.datetime) -> UpdateOne:
	"""サーバー情報の upsert 操作を生成する"""
	return UpdateOne({"_id": info.id}, _guild_set(info, now), upsert=True)


def _guild_set(info: GuildInfo, now: datetime.datetime) -> dict:
	"""サーバー情報の $set / $setOnInsert を生成する"""
	return {
		"$set": {
			"name": info.name,
			"member_count": info.member_count,
			"icon_url": info.icon_url,
			"updated_at": now,
		},
		"$setOnInsert": {"joined_at": info.joined_at or now},
	}


async def sync_guilds(guilds: Iterable[GuildInfo]) -> None:
	"""サーバー一覧を同期する (渡された一覧に無いサーバーは削除する。失敗しても起動処理は継続させる)"""
	try:
		infos = list(guilds)
		now = utcnow()
		if infos:
			await _collection("guilds").bulk_write([_guild_update(info, now) for info in infos], ordered=False)
		await _collection("guilds").delete_many({"_id": {"$nin": [info.id for info in infos]}})
	except Exception:
		logger.exception("サーバー一覧の同期に失敗")


async def upsert_guild(info: GuildInfo) -> None:
	"""サーバー1件を追加・更新する (失敗しても呼び出し元の処理は継続させる)"""
	try:
		await _collection("guilds").update_one({"_id": info.id}, _guild_set(info, utcnow()), upsert=True)
	except Exception:
		logger.exception("サーバー情報の更新に失敗")


async def remove_guild(guild_id: int) -> None:
	"""サーバー1件を削除する (失敗しても呼び出し元の処理は継続させる)"""
	try:
		await _collection("guilds").delete_one({"_id": guild_id})
	except Exception:
		logger.exception("サーバー情報の削除に失敗")


async def record_quiz_history(history: QuizHistory) -> None:
	"""クイズ履歴を記録する (失敗しても呼び出し元の処理は継続させる)"""
	try:
		await _collection("quiz_history").insert_one(
			{
				"guild_id": history.guild_id,
				"guild_name": history.guild_name,
				"channel_id": history.channel_id,
				"voice_channel_name": history.voice_channel_name,
				"owner_id": history.owner_id,
				"query": history.query,
				"question_total": history.question_total,
				"completed_questions": history.completed_questions,
				"participants": history.participants,
				"correct_counts": {str(user_id): count for user_id, count in history.correct_counts.items()},
				"started_at": history.started_at,
				"ended_at": history.ended_at,
			}
		)
	except Exception:
		logger.exception("クイズ履歴の記録に失敗")
