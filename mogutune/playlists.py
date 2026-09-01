# Copyright (c) 2026 Milkeyyy

from __future__ import annotations

import dataclasses
import datetime
import logging

logger = logging.getLogger(__name__)

MAX_PLAYLISTS_PER_GUILD = 50
"""サーバーごとのプレイリスト上限"""
MAX_TRACKS_PER_PLAYLIST = 500
"""1つのプレイリストの楽曲数上限"""
TRACK_ADD_SEPARATOR = " "
"""複数 URL 指定の区切り文字 (URL に生の空白は含まれないため安全)"""


@dataclasses.dataclass
class PlaylistTrack:
	"""プレイリストの楽曲 (管理用メタデータ)"""

	uri: str
	title: str = ""
	author: str = ""
	isrc: str | None = None
	chorus_ms: int | None = None
	"""サビ位置 (ミリ秒)。将来の手動設定用に予約 (現在は常に None)"""

	@classmethod
	def from_doc(cls, doc: object) -> PlaylistTrack | None:
		"""Mongo サブドキュメントから生成 (uri が欠損・非文字列の場合は None)"""
		if not isinstance(doc, dict):
			return None
		uri = doc.get("uri")
		if not isinstance(uri, str) or not uri:
			return None
		title = doc.get("title")
		author = doc.get("author")
		isrc = doc.get("isrc")
		chorus_ms = doc.get("chorus_ms")
		return cls(
			uri=uri,
			title=title if isinstance(title, str) else "",
			author=author if isinstance(author, str) else "",
			isrc=isrc if isinstance(isrc, str) else None,
			chorus_ms=chorus_ms if isinstance(chorus_ms, int) and chorus_ms >= 0 else None,
		)


@dataclasses.dataclass
class Playlist:
	"""サーバーごとのプレイリスト"""

	id: str
	guild_id: int
	name: str
	description: str
	author_id: int
	created_at: datetime.datetime
	tracks: list[PlaylistTrack]

	@classmethod
	def from_doc(cls, doc: dict | None) -> Playlist | None:
		"""Mongo ドキュメントから生成 (必須項目が欠損している場合は None)"""
		if not isinstance(doc, dict):
			return None
		_id = doc.get("_id")
		guild_id = doc.get("guild_id")
		name = doc.get("name")
		if not isinstance(_id, str) or not isinstance(guild_id, int) or not isinstance(name, str):
			return None
		description = doc.get("description")
		author_id = doc.get("author_id")
		created_at = doc.get("created_at")
		tracks_docs = doc.get("tracks")
		tracks: list[PlaylistTrack] = []
		if isinstance(tracks_docs, list):
			tracks = [t for t in (PlaylistTrack.from_doc(d) for d in tracks_docs) if t is not None]
		return cls(
			id=_id,
			guild_id=guild_id,
			name=name,
			description=description if isinstance(description, str) else "",
			author_id=author_id if isinstance(author_id, int) else 0,
			created_at=created_at if isinstance(created_at, datetime.datetime) else datetime.datetime.now(tz=datetime.UTC),
			tracks=tracks,
		)


def dedupe_track_docs(docs: list[dict]) -> list[dict]:
	"""楽曲サブドキュメントの一覧から URI 重複と URI 欠損を除去する (出現順保持)"""
	unique_docs: list[dict] = []
	seen_uris: set[str] = set()
	for doc in docs:
		uri = doc.get("uri")
		if not isinstance(uri, str) or uri in seen_uris:
			continue
		seen_uris.add(uri)
		unique_docs.append(doc)
	return unique_docs


if __name__ == "__main__":
	# from_doc / dedupe_track_docs の純粋ロジックの自己チェック
	assert PlaylistTrack.from_doc(None) is None  # noqa: S101
	assert PlaylistTrack.from_doc({}) is None  # noqa: S101
	assert PlaylistTrack.from_doc({"uri": "u", "title": 1, "isrc": "x"}).title == ""  # noqa: S101
	assert PlaylistTrack.from_doc({"uri": "u", "chorus_ms": -1}).chorus_ms is None  # noqa: S101
	assert PlaylistTrack.from_doc({"uri": "u", "chorus_ms": 0}).chorus_ms == 0  # noqa: S101
	assert Playlist.from_doc(None) is None  # noqa: S101
	assert Playlist.from_doc({"_id": "1", "guild_id": "x", "name": "n"}) is None  # noqa: S101
	pl = Playlist.from_doc(
		{
			"_id": "1",
			"guild_id": 123,
			"name": "n",
			"description": 1,
			"author_id": "x",
			"created_at": "bad",
			"tracks": [{"uri": "u"}, "invalid", {"uri": "u"}],
		}
	)
	assert pl is not None  # noqa: S101
	assert pl.description == ""  # noqa: S101
	assert pl.author_id == 0  # noqa: S101
	assert len(pl.tracks) == 2  # noqa: S101, PLR2004  (不正ドキュメント除外 + 重複は含めたまま from_doc は非重複化しない)
	assert dedupe_track_docs([{"uri": "a"}, {"uri": "a"}, {"uri": None}]) == [{"uri": "a"}]  # noqa: S101
	print("playlists self-check passed")  # noqa: T201
