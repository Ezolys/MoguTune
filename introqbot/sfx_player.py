import asyncio
import logging
from os import getenv

import mafic

logger = logging.getLogger(__name__)

SFX_SOURCE = "youtube"  # Or load from config


class SoundEffectPlayer:
	"""効果音を再生するためのクラス"""

	def __init__(self, player: mafic.Player):
		self.sfx_list = {  # キー: フルパス
			"SFX_QUIZ_CORRECT": "",
			"SFX_QUIZ_INCORRECT": "",
			"SFX_QUIZ_Q": "",
			"SFX_QUIZ_A": "",
		}
		self.player = player
		self.sfx_finished = asyncio.Event()

		# 環境変数からSFXを読み込む
		for key, path in self.sfx_list.items():
			self.sfx_list[key] = getenv(key, path)

	async def play_sfx(self, sfx_key: str) -> None:
		"""指定されたパスの効果音を再生します。

		再生中はメインの楽曲を一時停止し、再生後に再開します。
		"""
		# if not self.player.current:
		# 	logger.warning("No track is currently playing. Cannot play SFX.")
		# 	return

		if sfx_key not in self.sfx_list or not self.sfx_list[sfx_key]:
			logger.warning("Invalid or empty SFX key. Cannot play SFX: %s", sfx_key)
			return

		current_track = self.player.current
		current_position = self.player.position

		# メインの楽曲を一時停止
		await self.player.pause()

		try:
			# 効果音を再生
			sfx_path = self.sfx_list[sfx_key]
			sfx_track = await self.player.fetch_tracks(sfx_path, search_type=mafic.SearchType[SFX_SOURCE])
			if sfx_track is None or not isinstance(sfx_track, list):
				logger.warning("Failed to load SFX track. Cannot play SFX.")
				return

			if len(sfx_track) == 0:
				logger.warning("Failed to load SFX track. Cannot play SFX.")
				return

			sfx_track = sfx_track[0]

			# イベントリスナーを一時的に設定
			self.sfx_finished.clear()
			await self.player.play(sfx_track)

			# 効果音の再生完了を待つ
			await self.sfx_finished.wait()
		finally:
			# 元の楽曲を再開
			if current_track:
				await self.player.play(current_track, start_time=current_position, pause=False)
