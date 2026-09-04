# Copyright (c) 2026 Milkeyyy

from dataclasses import dataclass

from mogutune_core.models import Track as CoreTrack
from sonolink.models import Playable as SonoPlayable
from sonolink.models import Playlist as SonoPlaylist
from sonolink.models import SearchResult


@dataclass
class TrackCollection:
	"""session.play が受け取る楽曲コンテナ (sonolink.Playlist / DBプレイリスト共通)"""

	tracks: list[SonoPlayable]
	name: str
	plugin_info: dict | None = None


def to_core_track(track: SonoPlayable) -> CoreTrack:
	"""sonolink.Playable を core.Track へ変換する"""
	_isrc = track.isrc
	# ISRC がない場合は plugin_info から探してみる
	if _isrc is None:
		_plugin_info = getattr(track.data, "plugin_info", None)
		if _plugin_info:
			_isrc = _plugin_info.get("isrc")
	return CoreTrack(
		uri=track.uri,
		title=track.title,
		author=track.author,
		source=track.source_name,
		identifier=getattr(track, "identifier", None),
		artwork_url=track.artwork,
		isrc=_isrc,
		length_ms=getattr(track, "length", None),
	)


def to_core_tracks(tracks: list[SonoPlayable]) -> list[CoreTrack]:
	"""sonolink.Playable の一覧を core.Track の一覧へ変換する"""
	return [to_core_track(t) for t in tracks]


def to_sono_track(core_track: CoreTrack, source_tracks: list[SonoPlayable]) -> SonoPlayable | None:
	"""core.Track を URI で元の sonolink.Playable へ引き戻す (見つからない場合は None)"""
	for track in source_tracks:
		if track.uri is not None and track.uri == core_track.uri:
			return track
	return None


def to_sono_tracks(core_tracks: list[CoreTrack], source_tracks: list[SonoPlayable]) -> list[SonoPlayable]:
	"""core.Track の一覧を URI で元の sonolink.Playable の一覧へ引き戻す"""
	return [t for t in (to_sono_track(c, source_tracks) for c in core_tracks) if t is not None]


def to_stored_track_dict(track: SonoPlayable) -> dict:
	"""sonolink.Playable を DB の楽曲サブドキュメントへ変換する (管理用メタデータのみ)"""
	core = to_core_track(track)
	return {
		"uri": core.uri,
		"title": core.title,
		"author": core.author,
		"isrc": core.isrc,
		"chorus_ms": None,
	}


def unpack_search(result: SearchResult) -> SonoPlayable | list[SonoPlayable] | SonoPlaylist | None:
	"""SearchResult を正規化する (エラー・空結果は None)"""
	if result.is_error() or result.is_empty() or result.result is None:
		return None
	return result.result
