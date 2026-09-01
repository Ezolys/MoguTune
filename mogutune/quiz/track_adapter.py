# Copyright (c) 2026 Milkeyyy

from dataclasses import dataclass

from mafic import Track as MaficTrack
from mogutune_core.models import Track as CoreTrack


@dataclass
class TrackCollection:
	"""session.play が受け取る楽曲コンテナ (mafic.Playlist / DBプレイリスト共通)"""

	tracks: list[MaficTrack]
	name: str
	plugin_info: dict | None = None


def to_core_track(track: MaficTrack) -> CoreTrack:
	"""mafic.Track を core.Track へ変換する"""
	_isrc = getattr(track, "isrc", None)
	# ISRC がない場合は plugin_info から探してみる
	if _isrc is None and hasattr(track, "plugin_info") and track.plugin_info:
		_isrc = track.plugin_info.get("isrc")
	return CoreTrack(
		uri=track.uri,
		title=track.title,
		author=track.author,
		source=track.source,
		identifier=getattr(track, "identifier", None),
		artwork_url=track.artwork_url,
		isrc=_isrc,
		length_ms=getattr(track, "length", None),
	)


def to_core_tracks(tracks: list[MaficTrack]) -> list[CoreTrack]:
	"""mafic.Track の一覧を core.Track の一覧へ変換する"""
	return [to_core_track(t) for t in tracks]


def to_mafic_track(core_track: CoreTrack, source_tracks: list[MaficTrack]) -> MaficTrack | None:
	"""core.Track を URI で元の mafic.Track へ引き戻す (見つからない場合は None)"""
	for track in source_tracks:
		if track.uri is not None and track.uri == core_track.uri:
			return track
	return None


def to_mafic_tracks(core_tracks: list[CoreTrack], source_tracks: list[MaficTrack]) -> list[MaficTrack]:
	"""core.Track の一覧を URI で元の mafic.Track の一覧へ引き戻す"""
	return [t for t in (to_mafic_track(c, source_tracks) for c in core_tracks) if t is not None]


def to_stored_track_dict(track: MaficTrack) -> dict:
	"""mafic.Track を DB の楽曲サブドキュメントへ変換する (管理用メタデータのみ)"""
	core = to_core_track(track)
	return {
		"uri": core.uri,
		"title": core.title,
		"author": core.author,
		"isrc": core.isrc,
		"chorus_ms": None,
	}
