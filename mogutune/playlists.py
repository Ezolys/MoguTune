# Copyright (c) 2026 Milkeyyy

from __future__ import annotations

import dataclasses
import datetime

MAX_PLAYLISTS_PER_GUILD = 50
"""サーバーごとに登録できるプレイリストの上限"""


@dataclasses.dataclass
class Playlist:
	"""サーバーごとに登録されたお気に入りプレイリスト (URL と表示用メタデータのみ保持する)"""

	id: str
	guild_id: int
	name: str
	description: str
	url: str
	track_count: int
	author_id: int
	created_at: datetime.datetime

	@classmethod
	def from_doc(cls, doc: dict | None) -> Playlist | None:
		"""Mongo ドキュメントから生成 (必須項目が欠損している場合は None)"""
		if not isinstance(doc, dict):
			return None
		_id = doc.get("_id")
		guild_id = doc.get("guild_id")
		name = doc.get("name")
		url = doc.get("url")
		if not isinstance(_id, str) or not isinstance(guild_id, int) or not isinstance(name, str) or not isinstance(url, str) or not url:
			return None
		description = doc.get("description")
		track_count = doc.get("track_count")
		author_id = doc.get("author_id")
		created_at = doc.get("created_at")
		return cls(
			id=_id,
			guild_id=guild_id,
			name=name,
			description=description if isinstance(description, str) else "",
			url=url,
			track_count=track_count if isinstance(track_count, int) and track_count >= 0 else 0,
			author_id=author_id if isinstance(author_id, int) else 0,
			created_at=created_at if isinstance(created_at, datetime.datetime) else datetime.datetime.now(tz=datetime.UTC),
		)


if __name__ == "__main__":
	# from_doc の純粋ロジックの自己チェック
	assert Playlist.from_doc(None) is None  # noqa: S101
	assert Playlist.from_doc({}) is None  # noqa: S101
	assert Playlist.from_doc({"_id": "1", "guild_id": 123, "name": "n"}) is None  # noqa: S101  (url 欠損)
	assert Playlist.from_doc({"_id": "1", "guild_id": 123, "name": "n", "url": ""}) is None  # noqa: S101  (url 空)
	pl = Playlist.from_doc(
		{
			"_id": "1",
			"guild_id": 123,
			"name": "n",
			"description": 1,
			"url": "https://example.com/playlist",
			"track_count": -1,
			"author_id": "x",
			"created_at": "bad",
		}
	)
	assert pl is not None  # noqa: S101
	assert pl.description == ""  # noqa: S101
	assert pl.track_count == 0  # noqa: S101
	assert pl.author_id == 0  # noqa: S101
	print("playlists self-check passed")  # noqa: T201
