# Copyright (c) 2026 Milkeyyy

"""MongoDB への接続"""

from __future__ import annotations

from fastapi import Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase


def create_client(db_uri: str) -> AsyncMongoClient:
	"""MongoDB クライアントを生成する (読み出し日時を tz-aware にする)"""
	return AsyncMongoClient(host=db_uri, tz_aware=True)


def get_db(request: Request) -> AsyncDatabase:
	"""リクエストからデータベースを取得する (FastAPI 依存関係)"""
	return request.app.state.db
