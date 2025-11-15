import logging
import traceback
from os import getenv
from typing import ClassVar

from httpx import AsyncClient

logger = logging.getLogger(__name__)


class YTMostReplayedAPI:
	_API_URL: ClassVar[str] = getenv("YTMRAPI_URL", "http://localhost") + "/"
	cl = AsyncClient()

	@classmethod
	async def get_chorus_info(cls, youtube_url: str) -> int | None:
		"""YTMostReplayedAPI サビ部分のデータを取得して、再生位置 (ミリ秒) を返す"""
		logger.debug("YTMostReplayedAPI 情報取得")
		try:
			res = await cls.cl.get(
				cls._API_URL + "heatmap",
				params={"url": youtube_url},
				headers={"Secret": getenv("YTMRAPI_SECRET", "")},
				timeout=30,
			)
			if res.status_code == 200:
				d = res.json()
				if d.get("data") is not None:
					h = d.get("data")
					if h is not None:
						return h["start_time"] * 1000
		except Exception:
			logger.error("YTMostReplayedAPI 情報取得失敗")
			logger.error(traceback.format_exc())
		return None
