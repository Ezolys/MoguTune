import logging
import sys
import traceback
from os import getenv

import pymongo
import pymongo.asynchronous.collection
import pymongo.asynchronous.database
from pymongo import errors

logger = logging.getLogger(__name__)


class DBManager:
	_client: pymongo.AsyncMongoClient
	db: pymongo.asynchronous.database.AsyncDatabase
	col_presets: pymongo.asynchronous.collection.AsyncCollection

	@classmethod
	async def connect(cls) -> None:
		"""データベースへ接続する"""
		try:
			# データベース情報が設定されているかチェックする
			db_uri = getenv("DB_URI")
			db_name = getenv("DB_NAME")
			db_collection = "presets"
			db_settings = (db_uri, db_name, db_collection)
			# 1つでも設定されていないものがある場合はエラーを出力して終了する
			if not all(db_settings):
				logger.error("データベース接続失敗")
				for e in db_settings:
					if not e or e == "":
						logger.error("- 環境変数 %s が設定されていません", e)
				sys.exit(1)

			# 接続する
			logger.info("データベースへ接続")
			cls._client = pymongo.AsyncMongoClient(host=db_uri)
			# 最初の操作で接続が確立されるため、ここではpingを送信して接続を確認
			await cls._client.admin.command("ping")

			# データベース/コレクションを取得
			logger.info("- データベースを取得: %s", db_name)
			cls.db = cls._client.get_database(db_name)
			cls.col_presets = cls.db.get_collection(db_collection)
		except errors.ConnectionFailure as e:
			logger.error("データベース接続失敗: %s", e)
			sys.exit(1)
		except Exception:
			logger.error("データベース接続失敗")
			logger.error(traceback.format_exc())
			sys.exit(1)

	@classmethod
	async def disconnect(cls) -> None:
		"""データベースから切断する"""
		if hasattr(cls, "_client") and cls._client:
			logger.info("データベースから切断")
			await cls._client.close()
