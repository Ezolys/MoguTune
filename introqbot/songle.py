import logging
from typing import ClassVar

from httpx import AsyncClient

logger = logging.getLogger(__name__)


# TODO: キャッシュ実装
class SongleAPI:
	_API_URL: ClassVar[str] = "https://widget.songle.jp/api/v1/"
	cl = AsyncClient()

	@classmethod
	async def get_chorus_info(cls, youtube_url: str) -> float | None:
		"""Songle API から楽曲のサビに関するデータを取得して、最初のサビの秒数を返す"""
		logger.debug("Songle API サビ情報取得")
		res = await cls.cl.get(
			cls._API_URL + "song/chorus.json",
			params={"url": youtube_url},
		)
		if res.status_code == 200:
			d = res.json()
			cd = None
			cd_rep = None
			if d.get("chorusSegments") is not None and len(d.get("chorusSegments")) > 0:
				cd = d.get("chorusSegments")[0]
				if cd.get("isChorus"):
					cd_rep = cd.get("repeats")
					if cd_rep is not None and len(cd_rep) > 0:
						cd_rep = cd_rep[0].get("start")
						return cd_rep
		return None
