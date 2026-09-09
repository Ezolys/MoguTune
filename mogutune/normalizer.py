import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from os import getenv

import httpx
import sonolink
from mogutune_core.db import DBManager
from sonolink.models import Filters
from sonolink.models import Playable as SonoPlayable

from mogutune.track_adapter import resolve_youtube_url

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def _fenv(name: str, default: float) -> float:
	"""環境変数から float を読み込む (未設定・空文字・不正値は default)"""
	try:
		return float(getenv(name, str(default)))
	except ValueError:
		return default


# ラウドネスノーマライゼーション設定 (無効化で即時ロールバック可能)
ENABLED = getenv("NORMALIZE_ENABLED", "true").lower() == "true"
TARGET_LUFS = _fenv("NORMALIZE_TARGET_LUFS", -14)
MAX_BOOST_DB = _fenv("NORMALIZE_MAX_BOOST_DB", 8)
MAX_CUT_DB = _fenv("NORMALIZE_MAX_CUT_DB", 10)
LIMITER_MAX_AMPLITUDE = _fenv("NORMALIZE_LIMITER_MAX_AMPLITUDE", 0.95)
TIMEOUT_S = _fenv("NORMALIZE_TIMEOUT_S", 2.0)
PREFETCH_TIMEOUT_S = _fenv("NORMALIZE_PREFETCH_TIMEOUT_S", 60.0)
# クイズ開始前の解析進捗表示 (無効化する場合はコード内で False に変更する)
PROGRESS = True
API_URL = getenv("BACKEND_API_URL", "").rstrip("/")
API_SECRET = getenv("BACKEND_API_SECRET", "")

if ENABLED and not API_URL:
	logger.warning("BACKEND_API_URL が未設定のため LUFS 解析 API を呼び出しません (音量補正なしで動作します)")

_lru: dict[str, float] = {}
# ponytail: FIFO eviction (上限 512)、ヒット率が問題になったら OrderedDict ベースの真の LRU へ移行する
_LRU_MAX = 512
_HTTP_OK = 200

# 解析失敗の一時ネガティブキャッシュ (期限は time.monotonic 基準、同容量で FIFO 削除)
_neg_lru: dict[str, float] = {}
# ponytail: 実時間ベースの単純 TTL、ヒット率が問題になったら再設計する
_NEG_TTL_S = 30.0

_cl = httpx.AsyncClient()


def gain_to_volume(base: int, lufs: float) -> int:
	"""統合ラウドネス (LUFS) から再生音量を算出する (補正 dB を base に適用し 1..100 にクランプ)"""
	gain = min(MAX_BOOST_DB, max(-MAX_CUT_DB, TARGET_LUFS - lufs))
	return min(100, max(1, int(base * (10 ** (gain / 20)))))


def _cache_lru(uri: str, lufs: float) -> None:
	_lru[uri] = lufs
	while len(_lru) > _LRU_MAX:
		_lru.pop(next(iter(_lru)))


def _cache_negative(uri: str) -> None:
	_neg_lru[uri] = time.monotonic() + _NEG_TTL_S
	while len(_neg_lru) > _LRU_MAX:
		_neg_lru.pop(next(iter(_neg_lru)))


async def _mongo_lufs(uri: str) -> float | None:
	"""MongoDB loudness_cache から LUFS を読み込む (失敗・不在は None)"""
	try:
		doc = await DBManager.db.get_collection("loudness_cache").find_one({"_id": uri})
	except Exception:
		logger.exception("loudness_cache の読み込みに失敗しました: %s", uri)
		return None
	lufs = doc.get("lufs") if doc is not None else None
	return lufs if isinstance(lufs, (int, float)) else None


async def _mongo_save(uri: str, lufs: float) -> None:
	"""MongoDB loudness_cache へ保存する (失敗は無視)"""
	try:
		await DBManager.db.get_collection("loudness_cache").replace_one({"_id": uri}, {"_id": uri, "lufs": lufs}, upsert=True)
	except Exception:
		logger.exception("loudness_cache への保存に失敗しました: %s", uri)


async def _api_lufs(uri: str) -> float | None:
	"""外部解析 API から LUFS を取得する (失敗・未設定は None)"""
	try:
		res = await _cl.get(f"{API_URL}/lufs", params={"url": uri}, headers={"Secret": API_SECRET}, timeout=TIMEOUT_S)
		if res.status_code != _HTTP_OK:
			logger.debug("LUFS 解析 API が失敗: %s (status=%s)", uri, res.status_code)
			return None
		data = res.json().get("data")
		if isinstance(data, dict) and isinstance(data.get("lufs"), (int, float)):
			return float(data["lufs"])
		logger.debug("LUFS 解析 API のレスポンスに lufs がありません: %s", uri)
	except Exception:
		logger.debug("LUFS 解析 API のリクエストに失敗しました: %s", uri)
	return None


async def _resolve_lufs(uri: str) -> float | None:
	"""LUFS を解析してキャッシュに保存する (バックグラウンド解析タスク本体。解析完了で値不明ならネガティブキャッシュ)"""
	lufs = await _mongo_lufs(uri)
	if lufs is None and API_URL:
		lufs = await _api_lufs(uri)
		if lufs is not None:
			await _mongo_save(uri, lufs)
	if lufs is not None:
		_cache_lru(uri, lufs)
	else:
		_cache_negative(uri)
	return lufs


_inflight: dict[str, asyncio.Task[float | None]] = {}


def _get_or_start_task(uri: str) -> asyncio.Task[float | None]:
	"""URL の解析タスクを取得する (進行中のものがなければ起動する)"""
	task = _inflight.get(uri)
	if task is None:
		task = asyncio.create_task(_resolve_lufs(uri))
		_inflight[uri] = task
		task.add_done_callback(lambda _t, _uri=uri: _inflight.pop(_uri, None))
	return task


async def _lufs_for(uri: str) -> float | None:
	"""LUFS を取得する (LRU → ネガ → 進行中/新規解析タスク。タイムアウトしても解析はバックグラウンドで継続する)"""
	if uri in _lru:
		return _lru[uri]
	expiry = _neg_lru.get(uri)
	if expiry is not None:
		if time.monotonic() < expiry:
			return None
		del _neg_lru[uri]
	try:
		return await asyncio.wait_for(asyncio.shield(_get_or_start_task(uri)), TIMEOUT_S)
	except TimeoutError:
		return None


async def _analysis_url(track: SonoPlayable) -> str | None:
	"""解析 API に渡す URL を返す (Spotify 起源トラックは YouTube URL に解決、失敗は None)"""
	if track.uri is None:
		return None
	if track.source_name == "spotify":
		return await resolve_youtube_url(track)
	return track.uri


async def resolve_volume(track: SonoPlayable, base: int) -> int:
	"""トラックのラウドネス補正後の音量を返す (補正できない場合は base)"""
	if not ENABLED or track.uri is None:
		return base
	url = await _analysis_url(track)
	if url is None:
		return base
	lufs = await _lufs_for(url)
	if lufs is None:
		return base
	volume = gain_to_volume(base, lufs)
	logger.debug("LUFS 補正: %s lufs=%.1f volume=%s (base=%s)", url, lufs, volume, base)
	return volume


async def prefetch(
	tracks: list[SonoPlayable],
	progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> None:
	"""全トラックの解析 URL を解決し、LUFS 解析が完了するまで待つ (タイムアウト分はバックグラウンドで継続・失敗は無視)

	progress は解析完了ごとに (完了数, 総数) を受け取る。
	"""
	if not ENABLED or not API_URL:
		return
	# 解析 URL を並列解決 (Spotify 起源は Lavalink 検索。再解決は node キャッシュで高速)
	urls = [url for url in await asyncio.gather(*(_analysis_url(track) for track in tracks)) if url is not None]
	# 解析タスクを起動 (進行中のものは共有。キャッシュ済みは対象外)
	tasks = [_get_or_start_task(url) for url in dict.fromkeys(urls) if url not in _lru]
	total = len(tasks)
	if total == 0:
		return
	deadline = time.monotonic() + PREFETCH_TIMEOUT_S
	for done, task in enumerate(tasks, 1):
		remaining = deadline - time.monotonic()
		if remaining <= 0:
			break
		try:
			await asyncio.wait_for(asyncio.shield(task), remaining)
		except TimeoutError:
			break  # 残りはバックグラウンドで継続する
		except Exception:
			logger.debug("LUFS 解析タスクが失敗しました (進捗には数えます): %s", getattr(task, "get_name", lambda: "")())
		if progress is not None:
			await progress(done, total)


_prefetch_tasks: set[asyncio.Task[None]] = set()


def start_prefetch(tracks: list[SonoPlayable]) -> None:
	"""Prefetch をバックグラウンドで開始する (タスク参照を保持し GC による中断を防ぐ)"""
	task = asyncio.create_task(prefetch(tracks))
	_prefetch_tasks.add(task)
	task.add_done_callback(_prefetch_tasks.discard)


async def apply_normalization_limiter(player: sonolink.Player) -> None:
	"""ピークリミッター (LavaDSPX normalization) を適用する。失敗してもクイズを止めない

	LavaDSPX の normalization はピーク減衰専用 (静かな音のブーストはしない)。
	LUFS ターゲットへの補正は gain_to_volume の音量スケーリングが担い、本フィルターは
	ブースト後のピークを LIMITER_MAX_AMPLITUDE に頭打ちするだけのため、
	NORMALIZE_TARGET_LUFS 通りのラウドネスにはならない点に注意。
	またプレイヤー全体に掛かるため SFX にも作用する。
	"""
	if not ENABLED:
		return
	try:
		await player.set_filters(Filters(plugin_filters={"normalization": {"maxAmplitude": LIMITER_MAX_AMPLITUDE}}))
		logger.debug("LavaDSPX normalization リミッターを適用しました (maxAmplitude=%s)", LIMITER_MAX_AMPLITUDE)
	except Exception:
		logger.exception("LavaDSPX normalization リミッターの適用に失敗しました (補正なしで続行)")


if __name__ == "__main__":
	# gain_to_volume の純粋ロジックの自己チェック (モジュールの既定設定で検証する)
	base = 10
	assert gain_to_volume(base, TARGET_LUFS) == base  # noqa: S101  # ターゲット LUFS なら原音のまま
	assert gain_to_volume(base, -100) == int(base * 10 ** (MAX_BOOST_DB / 20))  # noqa: S101  # 小さすぎる音は最大ブースト
	assert gain_to_volume(base, 100) == int(base * 10 ** (-MAX_CUT_DB / 20))  # noqa: S101  # 大きすぎる音は最大カット
	assert gain_to_volume(1000, -100) == 100  # noqa: S101, PLR2004  # 上限クランプ
	assert gain_to_volume(0, -100) == 1  # noqa: S101  # 下限クランプ
	print("gain_to_volume self-check passed")  # noqa: T201
