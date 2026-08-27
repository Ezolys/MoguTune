# Copyright (c) 2026 Milkeyyy

"""ActivitySession のゲーム進行を検証する (mafic / Discord はモック)"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import mafic
import pytest
from mogutune_core.activity_protocol import (
	AdvanceMessage,
	AnswerMessage,
	BridgeUser,
	ClientRelayMessage,
	RaiseHandMessage,
	ServerRelayMessage,
	StartMessage,
	StateMessage,
	bridge_to_bot_adapter,
	bridge_to_server_adapter,
)
from mogutune_core.progression import Action, Mode

from mogutune.activity.manager import ActivitySessionManager
from mogutune.activity.session import ActivitySession

if TYPE_CHECKING:
	from collections.abc import Callable

	MessageFilter = Callable[[object], bool]


def _track_entry(uri: str, title: str, length: int = 240000) -> dict:
	return {
		"encoded": "AAAA",
		"info": {
			"identifier": uri,
			"isSeekable": True,
			"author": "Artist",
			"length": length,
			"isStream": False,
			"position": 0,
			"title": title,
			"uri": uri,
			"artworkUrl": "https://art.example/1.png",
			"isrc": None,
			"sourceName": "youtube",
		},
	}


def _playlist(count: int = 5) -> mafic.Playlist:
	return mafic.Playlist(
		info={"name": "test", "selectedTrack": -1},
		tracks=[_track_entry(f"https://youtube.com/watch?v=t{i}", f"Track {i}") for i in range(1, count + 1)],
		plugin_info={},
	)


class FakePlayer:
	def __init__(self, playlist: mafic.Playlist) -> None:
		self._playlist = playlist
		self.calls: list[tuple] = []
		self.playing: mafic.Track | None = None

	async def fetch_tracks(self, query: str, search_type: object = None) -> mafic.Playlist:
		del query, search_type
		return self._playlist

	async def play(self, track: mafic.Track, *, volume: int | None = None) -> None:
		del volume
		self.calls.append(("play", track.uri))
		self.playing = track

	async def pause(self) -> None:
		self.calls.append(("pause",))

	async def resume(self) -> None:
		self.calls.append(("resume",))

	async def stop(self) -> None:
		self.calls.append(("stop",))

	async def disconnect(self) -> None:
		self.calls.append(("disconnect",))


class EmitCollector:
	def __init__(self) -> None:
		self.messages: list[tuple[str, object, int | None]] = []

	async def emit(self, instance_id: str, message: object, user_id: int | None = None) -> None:
		self.messages.append((instance_id, message, user_id))

	def of_type(self, t: str) -> list[object]:
		return [m for _, m, _ in self.messages if getattr(m, "type", None) == t]


async def wait_for(collector: EmitCollector, t: str, deadline: float | None = None, match: MessageFilter | None = None) -> object:
	if deadline is None:
		deadline = time.monotonic() + 2.0
	while time.monotonic() < deadline:
		for message in collector.of_type(t):
			if match is None or match(message):
				return message
		await asyncio.sleep(0.01)
	message = f"メッセージ {t} が受信できませんでした"
	raise AssertionError(message)


@pytest.fixture
async def session() -> ActivitySession:
	emitter = EmitCollector()
	session = ActivitySession(1, 2, "inst", emitter.emit)
	session.emitter = emitter  # type: ignore[attr-defined] (テスト用)
	session.pl = FakePlayer(_playlist())
	task = asyncio.create_task(session.run())
	yield session
	await session.cancel()
	with pytest.raises(asyncio.CancelledError):
		await task


def _join(user_id: int) -> BridgeUser:
	return BridgeUser(id=user_id, username=f"user-{user_id}", avatar="", locale="ja")


async def test_full_game_flow(session: ActivitySession) -> None:
	"""開始 → 早押し → 正解 → 進行 → 全問終了まで一巡する"""
	await session.join(_join(1))
	await session.join(_join(2))
	session.handle(1, StartMessage(type="start", query="https://example.com/pl", q_count=2, mode=Mode.HOST))

	question = await wait_for(session.emitter, "question_start")  # type: ignore[attr-defined]
	assert question.q_number == 1
	player: FakePlayer = session.pl  # type: ignore[assignment]
	assert player.calls[0][0] == "play"
	first_uri = player.calls[0][1]

	# 早押し: user1 が先着
	session.handle(1, RaiseHandMessage(type="raise_hand"))
	answering = await wait_for(session.emitter, "answering")
	assert answering.user_id == 1
	assert len(answering.choices) == 5
	assert player.calls[-1] == ("pause",)

	# 正解
	session.handle(1, AnswerMessage(type="answer", uri=first_uri))
	result = await wait_for(session.emitter, "answer_result")
	assert result.correct is True
	assert player.calls[-1] == ("stop",)

	# 主催者が次へ
	session.handle(1, AdvanceMessage(type="advance", action=Action.NEXT))
	question2 = await wait_for(session.emitter, "question_start", match=lambda m: m.q_number == 2)
	assert question2.q_number == 2

	# 2問目: user2 が早押し → 不正解 → resume → 曲終了で自動スキップ (全問終了)
	session.handle(2, RaiseHandMessage(type="raise_hand"))
	answering2 = await wait_for(session.emitter, "answering", match=lambda m: m.user_id == 2)
	assert answering2.user_id == 2
	session.handle(2, AnswerMessage(type="answer", uri="https://wrong"))
	resume = await wait_for(session.emitter, "resume")
	assert resume.type == "resume"
	assert player.calls[-1] == ("resume",)

	session.on_track_finished(session.current_track)
	quiz_end = await wait_for(session.emitter, "quiz_end")
	assert len(quiz_end.ranking) == 2


async def test_incorrect_miss_and_track_end(session: ActivitySession) -> None:
	"""お手つき (miss) 中は早押しを拒否され、曲終了で自動スキップされる"""
	await session.join(_join(1))
	await session.join(_join(2))
	session.handle(1, StartMessage(type="start", query="q", q_count=2))
	await wait_for(session.emitter, "question_start")

	session.handle(1, RaiseHandMessage(type="raise_hand"))
	await wait_for(session.emitter, "answering")
	session.handle(1, AnswerMessage(type="answer", uri="https://wrong"))
	await wait_for(session.emitter, "resume")

	# miss 中は raise_hand がエラーになる (2人以上のとき)
	session.handle(1, RaiseHandMessage(type="raise_hand"))
	error = await wait_for(session.emitter, "error", match=lambda m: m.key == "view.q.answer_button.miss")
	assert error.key == "view.q.answer_button.miss"

	# 曲終了で次へ (答え非公開)
	session.on_track_finished(session.current_track)
	question2 = await wait_for(session.emitter, "question_start", match=lambda m: m.q_number == 2)
	assert question2.q_number == 2


async def test_track_exception_skips_question(session: ActivitySession) -> None:
	"""再生例外で問題がスキップされ答えが公開される"""
	await session.join(_join(1))
	session.handle(1, StartMessage(type="start", query="q", q_count=2))
	await wait_for(session.emitter, "question_start")

	session.on_track_exception(session.current_track)
	error = await wait_for(session.emitter, "error", match=lambda m: m.key == "activity.error.playback_failed")
	assert error.key == "activity.error.playback_failed"
	state = await wait_for(session.emitter, "state", match=lambda m: m.revealed_track is not None)
	assert state.revealed_track is not None


async def test_non_owner_cannot_start(session: ActivitySession) -> None:
	"""2人目の start は無視され、owner の start のみ受理される"""
	await session.join(_join(1))
	await session.join(_join(2))
	session.handle(1, StartMessage(type="start", query="q", q_count=2))
	await wait_for(session.emitter, "question_start")

	# 再 start (非オーナー) は無視される
	session.handle(2, StartMessage(type="start", query="q2", q_count=2))
	await asyncio.sleep(0.05)
	assert len(session.emitter.of_type("question_start")) == 1  # type: ignore[attr-defined]


async def test_manager_mapping() -> None:
	"""マネージャの instance → guild マッピングと破棄"""
	manager = ActivitySessionManager()
	session = manager.get_or_create(100, 200, "inst-x")
	assert manager.get(100) is session
	assert manager.guild_of("inst-x") == 100
	manager.forget(100, "inst-x")
	assert manager.get(100) is None
	assert manager.guild_of("inst-x") is None


def test_bridge_protocol_roundtrip() -> None:
	"""ブリッジプロトコルの JSON 往復 (シリアライズ → パース)"""
	message = ClientRelayMessage(type="client", instance_id="inst", user_id=1, message=RaiseHandMessage(type="raise_hand"))
	raw = message.model_dump_json()
	parsed = bridge_to_bot_adapter.validate_json(raw)
	assert parsed == message

	state = ServerRelayMessage(
		type="message",
		instance_id="inst",
		message=StateMessage(
			type="state",
			phase="lobby",
			mode="host",
			owner_id=None,
			players=[],
			q_number=0,
			q_count=0,
			current_answerer=None,
			answer_deadline=None,
			revealed_track=None,
			progression={"next": False, "skip": False, "end": False},
		),
	)
	raw2 = state.model_dump_json()
	parsed2 = bridge_to_server_adapter.validate_json(raw2)
	assert parsed2 == state
