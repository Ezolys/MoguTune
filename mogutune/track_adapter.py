# Copyright (c) 2026 Milkeyyy

import logging
import traceback
from dataclasses import dataclass

import sonolink
from mogutune_core.models import Track as CoreTrack
from sonolink.models import Playable as SonoPlayable
from sonolink.models import Playlist as SonoPlaylist
from sonolink.models import SearchResult

from mogutune.client import client

logger = logging.getLogger(__name__)


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
		if isinstance(_plugin_info, dict) and _plugin_info:
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


async def resolve_youtube_url(track: SonoPlayable) -> str | None:
	"""トラックを YouTube URL に解決する (youtube ソースは uri をそのまま返す。ISRC → ytmsearch → タイトル検索の順)

	サビ検出 (QuizSession.resolve_youtube_track_uri) と LUFS 解析の対象 URL 解決で共用する。
	"""
	if track.source_name == "youtube":
		return track.uri

	# ISRC を取得してみる (ない場合は plugin_info から探す)
	_isrc = track.isrc
	if _isrc is None:
		_plugin_info = getattr(track.data, "plugin_info", None)
		if isinstance(_plugin_info, dict) and _plugin_info:
			_isrc = _plugin_info.get("isrc")

	async def _search_first(query: str, source: sonolink.TrackSourceType) -> SonoPlayable | None:
		_search_result = unpack_search(await client.sl_client.search_track(query, source=source))
		if isinstance(_search_result, SonoPlayable):
			return _search_result
		if isinstance(_search_result, list) and _search_result:
			return _search_result[0]
		return None

	logger.info("Searching YouTube for: %s - %s (ISRC: %s)", track.author, track.title, _isrc)
	try:
		if _isrc:
			_found = await _search_first(f'"{_isrc}"', sonolink.TrackSourceType.YOUTUBE_MUSIC)
		else:
			_found = await _search_first(f"{track.author} - {track.title}", sonolink.TrackSourceType.YOUTUBE)
		if _found is not None:
			logger.info("Found YouTube track: %s", _found.uri)
			return _found.uri
		if _isrc:  # ISRC で見つからなかった場合はタイトルで再検索
			_found = await _search_first(f"{track.author} - {track.title}", sonolink.TrackSourceType.YOUTUBE)
			if _found is not None:
				logger.info("Found YouTube track (Title): %s", _found.uri)
				return _found.uri
	except Exception:
		logger.error("Failed to search YouTube track.")
		logger.error(traceback.format_exc())
	return None
