import json
from functools import cache
from pathlib import Path
from urllib.parse import ParseResult, parse_qs, urlencode, urlparse, urlunparse

LOCALES_DIR = Path(__file__).resolve().parent / "resources" / "locales"
DEFAULT_LOCALE = "en_GB"
LABEL_FORMAT_KEY = "cmd.play.query_url_label"
PLATFORM_LOCALE_KEYS = {
	"spotify": "cmd.play.query_url_platform.spotify",
	"youtube": "cmd.play.query_url_platform.youtube",
	"soundcloud": "cmd.play.query_url_platform.soundcloud",
}
URL_TYPE_LOCALE_KEYS = {
	"playlist": "cmd.play.query_url_type.playlist",
	"album": "cmd.play.query_url_type.album",
	"artist": "cmd.play.query_url_type.artist",
	"track": "cmd.play.query_url_type.track",
	"video": "cmd.play.query_url_type.video",
	"channel": "cmd.play.query_url_type.channel",
	"show": "cmd.play.query_url_type.show",
	"episode": "cmd.play.query_url_type.episode",
}
SPOTIFY_URL_TYPES = {"playlist", "album", "artist", "track", "show", "episode"}
SPOTIFY_USER_PLAYLIST_PATH_LENGTH = 3
SOUNDCLOUD_SPECIAL_PATHS = {"albums", "likes", "popular-tracks", "reposts", "sets", "tracks"}
AUTOCOMPLETE_CHOICE_VALUE_MAX_LENGTH = 100


def _normalize_url(url: str) -> str:
	return url.strip().strip("<>")


def _normalize_locale(locale: str | None) -> str:
	if locale is None:
		return DEFAULT_LOCALE
	normalized_locale = locale.replace("-", "_")
	if normalized_locale.startswith("ja"):
		return "ja"
	if not (LOCALES_DIR / f"{normalized_locale}.json").exists():
		return DEFAULT_LOCALE
	return normalized_locale


@cache
def _get_locale_strings(locale: str) -> dict[str, str]:
	with (LOCALES_DIR / f"{locale}.json").open(encoding="utf-8") as locale_file:
		locale_data = json.load(locale_file)
	return locale_data["strings"]


def _get_localized_value(key: str, locale: str | None) -> str | None:
	strings = _get_locale_strings(_normalize_locale(locale))
	default_strings = _get_locale_strings(DEFAULT_LOCALE)
	return strings.get(key, default_strings.get(key))


def _build_url_value(parsed_url: ParseResult, query_keys: tuple[str, ...] = ()) -> str:
	query = parse_qs(parsed_url.query)
	filtered_query = {key: query[key] for key in query_keys if key in query}
	return urlunparse(
		(
			parsed_url.scheme,
			parsed_url.netloc,
			parsed_url.path,
			"",
			urlencode(filtered_query, doseq=True),
			"",
		)
	)


def _format_choice_label(url_type: str, platform: str, locale: str | None) -> str | None:
	url_type_key = URL_TYPE_LOCALE_KEYS.get(url_type)
	platform_key = PLATFORM_LOCALE_KEYS.get(platform)
	if url_type_key is None or platform_key is None:
		return None

	label_format = _get_localized_value(LABEL_FORMAT_KEY, locale)
	localized_url_type = _get_localized_value(url_type_key, locale)
	localized_platform = _get_localized_value(platform_key, locale)
	if label_format is None or localized_url_type is None or localized_platform is None:
		return None
	return label_format.format(localized_url_type, localized_platform)


def _normalize_url_host(url: str) -> str:
	return urlparse(_normalize_url(url)).netloc.lower().split(":", maxsplit=1)[0]


def _get_youtube_url_type(url: str) -> str | None:
	parsed = urlparse(_normalize_url(url))
	query = parse_qs(parsed.query)
	path_parts = [part for part in parsed.path.split("/") if part]
	url_type = None

	if query.get("list"):
		url_type = "playlist"
	elif _normalize_url_host(url) == "youtu.be":
		url_type = "video"
	elif path_parts:
		if path_parts[0] in {"watch", "shorts", "live"}:
			url_type = "video"
		elif path_parts[0] == "playlist":
			url_type = "playlist"
		elif path_parts[0] in {"channel", "c", "user"} or path_parts[0].startswith("@"):
			url_type = "channel"
	return url_type


def _get_spotify_url_type(url: str) -> str | None:
	parsed = urlparse(_normalize_url(url))
	path_parts = [part for part in parsed.path.split("/") if part]

	if not path_parts:
		return None
	if path_parts[0].startswith("intl-") and len(path_parts) > 1:
		path_parts = path_parts[1:]
	if len(path_parts) >= SPOTIFY_USER_PLAYLIST_PATH_LENGTH and path_parts[0] == "user" and path_parts[2] == "playlist":
		return "playlist"
	if path_parts[0] in SPOTIFY_URL_TYPES:
		return path_parts[0]
	return None


def _get_soundcloud_url_type(url: str) -> str | None:
	path_parts = [part for part in urlparse(_normalize_url(url)).path.split("/") if part]

	if not path_parts:
		return None
	if path_parts[0] in {"discover", "search", "you"}:
		return None

	second_path_part = path_parts[1] if len(path_parts) > 1 else None
	if len(path_parts) == 1 or second_path_part in SOUNDCLOUD_SPECIAL_PATHS:
		if second_path_part in {"sets", "albums"}:
			return "playlist"
		return "artist"
	return "track"


def _get_autocomplete_url_value(url: str) -> str | None:
	url = _normalize_url(url)
	parsed = urlparse(url)
	host = _normalize_url_host(url)

	if host == "open.spotify.com" or host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"} or host == "youtu.be":
		value = _build_url_value(parsed)
	elif host in {"youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com"}:
		query_keys = ("list",) if parsed.path == "/playlist" else ("v", "list")
		value = _build_url_value(parsed, query_keys)
	else:
		return None

	if len(value) > AUTOCOMPLETE_CHOICE_VALUE_MAX_LENGTH:
		return None
	return value


def get_url_choice_label(url: str, locale: str | None) -> str | None:
	url = _normalize_url(url)
	host = _normalize_url_host(url)
	url_type = None
	platform = None

	if host == "open.spotify.com":
		url_type = _get_spotify_url_type(url)
		platform = "spotify"
	elif host in {"youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be"}:
		url_type = _get_youtube_url_type(url)
		platform = "youtube"
	elif host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"}:
		url_type = _get_soundcloud_url_type(url)
		platform = "soundcloud"

	if url_type is None or platform is None:
		return None

	return _format_choice_label(url_type, platform, locale)


def get_url_autocomplete_choice(url: str, locale: str | None) -> tuple[str, str] | None:
	label = get_url_choice_label(url, locale)
	if label is None:
		return None

	value = _get_autocomplete_url_value(url)
	if value is None:
		return None

	return label, value
