# Copyright (c) 2026 Milkeyyy

from __future__ import annotations

import dataclasses
import logging
from typing import get_type_hints

from mogutune_core.db import DBManager

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class GuildSettings:
	"""ギルドごとのクイズ設定"""

	artist_in_answers: bool = False
	"""解答候補にアーティスト名を含めるか"""
	progression_mode: str = "vote"
	"""進行方式 ("host" | "vote")"""
	ready_threshold: str = "majority"
	"""クイズ開始の準備完了条件 ("all" | "majority")"""

	@classmethod
	def from_doc(cls, doc: dict | None) -> GuildSettings:
		"""Mongo ドキュメントから生成 (未知キーは無視、型不一致・不正値はデフォルトへ)"""
		if doc is None:
			return cls()
		types = get_type_hints(cls)
		result = {}
		for field in dataclasses.fields(cls):
			value = doc.get(field.name)
			if not isinstance(value, types[field.name]):
				continue
			# 許可された値以外はデフォルトへフォールバックする
			if field.name in _FIELD_VALUE_CHOICES and value not in _FIELD_VALUE_CHOICES[field.name]:
				continue
			result[field.name] = value
		return cls(**result)


# 選択式 (str) 設定項目の許可値 (キー: フィールド名)
_FIELD_VALUE_CHOICES: dict[str, tuple[str, ...]] = {
	"progression_mode": ("host", "vote"),
	"ready_threshold": ("all", "majority"),
}


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
		# DB へ書き込んでからキャッシュを再構築する (書込失敗時にキャッシュと DB が乖離しないように)
		await DBManager.col_guild_settings.update_one({"_id": guild_id}, {"$set": kwargs}, upsert=True)
		doc = await DBManager.col_guild_settings.find_one({"_id": guild_id})
		settings = GuildSettings.from_doc(doc)
		self.settings[guild_id] = settings
		logger.debug("ギルド設定を更新: %d - %s", guild_id, kwargs)
		return settings


guild_settings_manager = GuildSettingsManager()


if __name__ == "__main__":
	# from_doc の純粋ロジックの自己チェック
	assert GuildSettings.from_doc(None).artist_in_answers is False  # noqa: S101
	assert GuildSettings.from_doc({"_id": 123, "artist_in_answers": True, "unknown": 1}).artist_in_answers is True  # noqa: S101
	assert GuildSettings.from_doc({"artist_in_answers": "x"}).artist_in_answers is False  # noqa: S101
	assert GuildSettings.from_doc({"artist_in_answers": 0}).artist_in_answers is False  # noqa: S101
	# 選択式設定項目のデフォルト
	_default = GuildSettings()
	assert _default.progression_mode == "vote"  # noqa: S101
	assert _default.ready_threshold == "majority"  # noqa: S101
	# 選択式設定項目の値検証 (不正値はデフォルトへ)
	assert GuildSettings.from_doc({"progression_mode": "host"}).progression_mode == "host"  # noqa: S101
	assert GuildSettings.from_doc({"progression_mode": "bogus"}).progression_mode == "vote"  # noqa: S101
	assert GuildSettings.from_doc({"progression_mode": 1}).progression_mode == "vote"  # noqa: S101
	assert GuildSettings.from_doc({"ready_threshold": "all"}).ready_threshold == "all"  # noqa: S101
	assert GuildSettings.from_doc({"ready_threshold": "bogus"}).ready_threshold == "majority"  # noqa: S101
	assert GuildSettings.from_doc({"ready_threshold": None}).ready_threshold == "majority"  # noqa: S101
	print("settings self-check passed")  # noqa: T201
