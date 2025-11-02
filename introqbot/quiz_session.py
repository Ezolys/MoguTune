from dataclasses import dataclass, field


@dataclass
class Player:
	"""クイズのプレイヤー (参加者)"""

	id: int
	"""プレイヤーのID"""
	point: int = 0
	"""ポイント (正答数)"""
	miss: bool = False
	"""不正解フラグ"""

	def correct(self) -> None:
		"""ポイントを1増やす"""
		self.point += 1

	def incorrect(self) -> None:
		"""不正解フラグを立てる"""
		self.miss = True

	def incorrect_reset(self) -> None:
		"""不正解フラグを消す"""
		self.miss = False

	def reset(self) -> None:
		"""ポイントと不正解フラグをリセット"""
		self.point = 0
		self.miss = False


@dataclass
class Session:
	"""クイズのセッション"""

	channel_id: int
	"""クイズが実行されているボイスチャンネルのID"""
	players: list[Player] = field(default_factory=list)
	"""参加するプレイヤーの一覧"""
	queue: list[int] = field(default_factory=list)
	"""参加待ちのプレイヤーのID"""

	def add_player(self, user_id: int) -> None:
		"""プレイヤーを追加"""
		self.players.append(Player(user_id))

	def remove_player(self, user_id: int) -> None:
		"""プレイヤーを削除"""
		self.players = [player for player in self.players if player.id != user_id]

	def add_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを追加"""
		self.queue.append(user_id)

	def remove_queue(self, user_id: int) -> None:
		"""参加待ちのプレイヤーを削除"""
		self.queue.remove(user_id)

	def join_queued_players(self) -> None:
		"""参加待ちのプレイヤー全員を参加させる"""
		for user_id in self.queue:
			self.add_player(user_id)
		self.queue = []

	def is_player_joined(self, user_id: int) -> bool:
		"""プレイヤーが参加しているかどうかを返す"""
		return user_id in [player.id for player in self.players]

	def refresh(self) -> None:
		"""全プレイヤーの不正解フラグをリセット"""
		[player.incorrect_reset() for player in self.players]

	def reset(self) -> None:
		"""全プレイヤーのポイントと不正解フラグをリセット"""
		[player.reset() for player in self.players]


@dataclass
class QuizSessionManager:
	"""クイズのセッションマネージャー"""

	sessions: dict[int, Session] = field(default_factory=dict)

	def create_session(self, channel_id: int) -> Session:
		"""セッションを新規作成"""
		self.sessions[channel_id] = Session(channel_id)
		return self.sessions[channel_id]

	def delete_session(self, channel_id: int) -> None:
		"""セッションを削除"""
		del self.sessions[channel_id]

	def get_session(self, channel_id: int) -> Session | None:
		"""セッションを取得

		存在しない場合は None を返す
		"""
		return self.sessions.get(channel_id)
