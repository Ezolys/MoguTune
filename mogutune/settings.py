# Copyright (c) 2026 Milkeyyy

from __future__ import annotations

import dataclasses
import logging

from mogutune_core.db import DBManager

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class GuildSettings:
	"""ギルドごとのクイズ設定"""

	artist_in_answers: bool = False
	"""解答候補にアーティスト名を含めるか"""

	@classmethod
	def from_doc(cls, doc: dict | None) -> GuildSettings:
		"""Mongo ドキュメントから生成 (未知キーは無視、欠損はデフォルト)"""
		if doc is None:
			return cls()
		field_names = {f.name for f in dataclasses.fields(cls)}
		return cls(**{k: v for k, v in doc.items() if k in field_names})


@dataclasses.dataclass
class GuildSettingsManager:
	settings: dict[int, GuildSettings] = dataclasses.field(default_factory=dict)
	"""設定のキャッシュ"""

	async def get(self, guild_id: int) -> GuildSettings:
		"""ギルド設定を取得する (read-through キャッシュ)"""
		cached = self.settings.get(guild_id)
		if cached is not None:
			return cached
		logger.debug("ギルド設定を取得: %d", guild_id)
		doc = await DBManager.col_guild_settings.find_one({"_id": guild_id})
		settings = GuildSettings.from_doc(doc)
		self.settings[guild_id] = settings
		return settings

	async def set(self, guild_id: int, **kwargs: object) -> GuildSettings:
		"""ギルド設定を更新する (未知のキーは ValueError)"""
		field_names = {f.name for f in dataclasses.fields(GuildSettings)}
		invalid = set(kwargs) - field_names
		if invalid:
			message = f"不正な設定項目: {sorted(invalid)}"
			raise ValueError(message)
		settings = await self.get(guild_id)
		for key, value in kwargs.items():
			setattr(settings, key, value)
		logger.debug("ギルド設定を更新: %d - %s", guild_id, kwargs)
		await DBManager.col_guild_settings.update_one({"_id": guild_id}, {"$set": kwargs}, upsert=True)
		return settings


guild_settings_manager = GuildSettingsManager()


if __name__ == "__main__":
	# from_doc の純粋ロジックの自己チェック
	assert GuildSettings.from_doc(None).artist_in_answers is False  # noqa: S101
	assert GuildSettings.from_doc({"_id": 123, "artist_in_answers": True, "unknown": 1}).artist_in_answers is True  # noqa: S101
	assert GuildSettings.from_doc({"artist_in_answers": "x"}).artist_in_answers == "x"  # noqa: S101
	print("settings self-check passed")  # noqa: T201
