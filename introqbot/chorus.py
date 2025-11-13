import logging
import math
import traceback
from operator import itemgetter
from os import getenv
from typing import ClassVar

from httpx import AsyncClient

logger = logging.getLogger(__name__)


class YTMostReplayedAPI:
	_API_URL: ClassVar[str] = getenv("YTMRAPI_URL", "localhost") + "/"
	cl = AsyncClient()

	@classmethod
	def find_chorus_with_sliding_window(cls, heatmap, window_seconds=15):
		"""スライディングウィンドウ法を使って、heatmapデータからサビの開始時間を推定する。

		Args:
		    heatmap (list): YouTubeのheatmapデータ。
		    window_seconds (int): サビの長さを想定したウィンドウの秒数。

		Returns:
		    dict: 最も平均値が高かった区間の開始データポイント。

		"""
		if not heatmap:
			return None

		# 1データポイントあたりの秒数を計算（end_time - start_time）
		# データが等間隔であることを前提とする
		seconds_per_point = heatmap[0]["end_time"] - heatmap[0]["start_time"]
		if seconds_per_point <= 0:
			return heatmap[0]  # 不正なデータの場合は先頭を返す

		# 秒数をデータポイント数に変換
		window_size = math.ceil(window_seconds / seconds_per_point)

		max_avg_value = -1
		best_start_index = -1

		# ウィンドウをスライドさせながら平均値を計算
		for i in range(len(heatmap) - window_size + 1):
			# 現在のウィンドウに含まれるデータ
			current_window = heatmap[i : i + window_size]

			# ウィンドウ内のvalueの合計を計算
			sum_of_values = sum(point["value"] for point in current_window)

			# 平均値を計算
			avg_value = sum_of_values / window_size

			if avg_value > max_avg_value:
				max_avg_value = avg_value
				best_start_index = i

		if best_start_index != -1:
			return heatmap[best_start_index]
		return None

	@classmethod
	async def get_chorus_info(cls, youtube_url: str) -> int | None:
		"""YTMostReplayedAPI からリプレイ回数が最も多い部分のデータを取得して、再生位置 (ミリ秒) を返す"""
		logger.debug("YTMostReplayedAPI 情報取得")
		try:
			res = await cls.cl.get(
				cls._API_URL + "getheatmap",
				params={"url": youtube_url},
				headers={"Secret": getenv("YTMRAPI_SECRET", "")},
				timeout=30,
			)
			if res.status_code == 200:
				d = res.json()
				if d.get("data"):
					h = cls.find_chorus_with_sliding_window(d["data"], window_seconds=20)
					if h is not None:
						return h["start_time"] * 1000
					# ヒートマップの一覧からリプレイ回数が最も多い部分を抽出して返す
					# return int(max(d["data"], key=itemgetter("value"))["start_time"]) * 1000  # ミリ秒
		except Exception:
			logger.error("YTMostReplayedAPI 情報取得失敗")
			logger.error(traceback.format_exc())
		return None
