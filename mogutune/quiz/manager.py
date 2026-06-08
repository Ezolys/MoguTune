import logging
import traceback
from dataclasses import dataclass, field

import mafic

from mogutune.debug_logger import DebugLogger
from mogutune.quiz.session import QuizSession

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@dataclass
class QuizSessionManager:
	"""クイズのセッションマネージャー"""

	sessions: dict[int, QuizSession] = field(default_factory=dict)

	def create_session(self, guild_id: int, channel_id: int, player: mafic.Player, query: str) -> QuizSession:
		"""セッションを新規作成する"""
		logger.debug(f"セッション新規作成: {guild_id}/{channel_id}")
		self.sessions[guild_id] = QuizSession(guild_id, channel_id, player, query)
		return self.sessions[guild_id]

	def delete_session(self, guild_id: int) -> None:
		"""セッションを削除する"""
		logger.debug(f"セッション削除: {guild_id}")
		if guild_id in self.sessions:
			del self.sessions[guild_id]

	def get_session(self, guild_id: int) -> QuizSession | None:
		"""セッションを取得する

		存在しない場合は None を返す
		"""
		return self.sessions.get(guild_id)

	async def end_session(self, guild_id: int) -> None:
		"""セッションを終了して削除する"""
		logger.debug(f"セッション終了: {guild_id}")
		if guild_id in self.sessions:
			session = self.sessions[guild_id]
			await self.sessions[guild_id].end()
			self.delete_session(guild_id)
			# ボイスチャンネルから切断する
			try:
				if session.voice_channel is not None and session.voice_channel.guild.voice_client is not None:
					await session.voice_channel.guild.voice_client.disconnect()
			except Exception:
				logger.error("- ボイスチャンネル切断エラー")
				logger.error(traceback.format_exc())
				await DebugLogger.report_internal_error(traceback.format_exc())


quiz_session_manager = QuizSessionManager()
