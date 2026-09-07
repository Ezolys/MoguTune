import asyncio
import logging
import time
from os import getenv

import httpx
import sonolink
from mogutune_core.db import DBManager
from sonolink.models import Filters
from sonolink.models import Playable as SonoPlayable

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
API_URL = getenv("NORMALIZE_API_URL", "").rstrip("/")
API_SECRET = getenv("NORMALIZE_API_SECRET", "")

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


async def _lufs_for(uri: str) -> float | None:
	"""LUFS を ①LRU → ②Mongo loudness_cache → ③外部解析 API の順で取得する (失敗は一時的にネガティブキャッシュ)"""
	if uri in _lru:
		return _lru[uri]
	expiry = _neg_lru.get(uri)
	if expiry is not None:
		if time.monotonic() < expiry:
			return None
		del _neg_lru[uri]
	lufs = await _mongo_lufs(uri)
	if lufs is not None:
		_cache_lru(uri, lufs)
		return lufs
	if API_URL:
		lufs = await _api_lufs(uri)
		if lufs is not None:
			_cache_lru(uri, lufs)
			await _mongo_save(uri, lufs)
		else:
			_cache_negative(uri)
	return lufs


async def resolve_volume(track: SonoPlayable, base: int) -> int:
	"""トラックのラウドネス補正後の音量を返す (補正できない場合は base)"""
	if not ENABLED or track.uri is None:
		return base
	lufs = await _lufs_for(track.uri)
	if lufs is None:
		return base
	volume = gain_to_volume(base, lufs)
	logger.debug("LUFS 補正: %s lufs=%.1f volume=%s (base=%s)", track.uri, lufs, volume, base)
	return volume


async def prefetch(tracks: list[SonoPlayable]) -> None:
	"""全トラックの LUFS を並列先読みしてキャッシュを温める (解析中は待たない・失敗は無視)"""
	if not ENABLED or not API_URL:
		return
	semaphore = asyncio.Semaphore(10)

	async def _prefetch(track: SonoPlayable) -> None:
		if track.uri is None:
			return
		async with semaphore:
			await _lufs_for(track.uri)

	await asyncio.gather(*(_prefetch(track) for track in tracks))


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
		await player.set_filters(Filters(plugin_filters={"normalization": {"maxAmplitude": LIMITER_MAX_AMPLITUDE, "adaptive": True}}))
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
