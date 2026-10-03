# Copyright (c) 2026 Milkeyyy

import asyncio
import contextlib
import logging
from dataclasses import dataclass

import discord
from discord.utils import MISSING

from mogutune.debug_logger import DebugLogger

logger = logging.getLogger(__name__)

APPLY_DEBOUNCE_SECONDS = 0.2
"""連続した状態変更を1回の編集にまとめるための待ち時間 (秒)"""

VERIFY_DELAY_SECONDS = 0.7
"""編集が反映されたかを確認するまでの待ち時間 (秒)"""

REAPPLY_DELAY_SECONDS = 1.5
"""反映されていない場合に再適用するまでの待ち時間 (秒)"""

MAX_APPLY_ATTEMPTS = 3
"""1つの状態を適用する最大試行回数"""


def _component_signature(components: list[dict[str, object]]) -> list[tuple[str | None, bool]]:
	"""コンポーネント (入れ子含む) の custom_id と disabled の並びを返す"""
	signature: list[tuple[str | None, bool]] = []
	for component in components:
		children = component.get("components")
		if isinstance(children, list) and children:
			signature.extend(_component_signature(children))
			continue
		custom_id = component.get("custom_id")
		signature.append((custom_id if isinstance(custom_id, str) else None, bool(component.get("disabled", False))))
	return signature


def _embed_signature(embed: discord.Embed | None) -> tuple[str, str, str | None]:
	"""埋め込みの表示内容 (タイトル・説明・画像URL) を返す"""
	if embed is None:
		return ("", "", None)
	image_url = embed.image.url if embed.image is not None else None
	return (embed.title or "", embed.description or "", image_url)


@dataclass
class _MessageState:
	"""メッセージに表示したい状態"""

	embed: discord.Embed
	view: discord.ui.View | None


class QuizMessageWriter:
	"""メッセージ編集を直列化・合流し、反映されるまで再適用する単一ライター

	Discord側で編集が巻き戻る事象 (discord-api-docs #7980 / #8631) への対策として、
	同じメッセージへの編集を1つのワーカーから順に送信し、編集後に反映を確認して
	反映されていなければ再適用する。進行判定は呼び出し側の状態を正とするため、
	ここでの反映失敗は進行を止めない。
	"""

	def __init__(self, message: discord.Message, *, guild_id: int, label: str) -> None:
		self._message = message
		self._guild_id = guild_id
		self._label = label
		self._desired: _MessageState | None = None
		self._dirty = asyncio.Event()
		self._closed = False
		self._reported_not_reflected = False
		self._task = asyncio.create_task(self._run(), name=f"quiz-message-writer-{message.id}")
		self._task.add_done_callback(self._on_task_done)

	def set_state(self, embed: discord.Embed, view: discord.ui.View | None = MISSING) -> None:
		"""表示したい状態を設定する (実際の編集はワーカーが直列に行う)"""
		if self._closed:
			return
		self._desired = _MessageState(embed=embed, view=view)
		self._dirty.set()

	def close(self) -> None:
		"""ライターを停止する (保留中の編集は破棄する)"""
		if self._closed:
			return
		self._closed = True
		self._dirty.set()
		self._task.cancel()

	def _on_task_done(self, task: asyncio.Task) -> None:
		"""ワーカーが異常終了した場合にログへ残す"""
		if task.cancelled():
			return
		exception = task.exception()
		if exception is not None:
			logger.error("%s: ライターの処理が異常終了しました: %r", self._label, exception)

	async def _run(self) -> None:
		"""最新の状態を直列に適用するワーカー"""
		while not self._closed:
			await self._dirty.wait()
			# 連続する状態変更をまとめる (途中状態は最新の状態で上書きする)
			await asyncio.sleep(APPLY_DEBOUNCE_SECONDS)
			self._dirty.clear()
			state = self._desired
			if state is not None:
				await self._apply(state)

	async def _apply(self, state: _MessageState) -> None:
		"""状態を適用し、反映されるまで再適用する"""
		for attempt in range(1, MAX_APPLY_ATTEMPTS + 1):
			fields: dict[str, object] = {"embed": state.embed}
			if state.view is not MISSING:
				fields["view"] = state.view

			try:
				await self._message.edit(**fields)
			except discord.errors.NotFound:
				self._closed = True
				return
			except Exception as e:
				logger.warning("%s: メッセージ編集に失敗 (%d/%d): %s", self._label, attempt, MAX_APPLY_ATTEMPTS, e)
				await asyncio.sleep(REAPPLY_DELAY_SECONDS)
				continue

			# より新しい状態が設定されている場合は、この状態の反映確認は行わない
			if self._desired is not state:
				return
			await asyncio.sleep(VERIFY_DELAY_SECONDS)
			if self._desired is not state or self._closed:
				return
			if await self._is_reflected(state):
				return
			logger.warning("%s: 編集が反映されませんでした (試行 %d/%d)", self._label, attempt, MAX_APPLY_ATTEMPTS)
			await asyncio.sleep(REAPPLY_DELAY_SECONDS)
		await self._report_not_reflected(state)

	async def _is_reflected(self, state: _MessageState) -> bool:
		"""編集内容がメッセージに反映されているかを確認する (確認不能な場合は反映済みとして扱う)"""
		try:
			fetched = await self._message.channel.fetch_message(self._message.id)
		except discord.errors.NotFound:
			self._closed = True
			return True
		except Exception:
			logger.debug("%s: 編集の反映確認に失敗しました", self._label, exc_info=True)
			return True

		if state.view is not MISSING:
			expected = [] if state.view is None else _component_signature(state.view.to_components())
			actual = _component_signature([component.to_dict() for component in fetched.components])
			if expected != actual:
				return False

		fetched_embed = fetched.embeds[0] if fetched.embeds else None
		return _embed_signature(state.embed) == _embed_signature(fetched_embed)

	async def _report_not_reflected(self, state: _MessageState) -> None:
		"""再適用しても反映されなかった場合に内部エラーとして記録する (ライターにつき1回)"""
		if self._closed or self._desired is not state or self._reported_not_reflected:
			return
		self._reported_not_reflected = True
		logger.warning("%s: 編集を再適用しても反映されませんでした (message=%s)", self._label, self._message.id)
		with contextlib.suppress(Exception):
			await DebugLogger.report_internal_error(
				f"メッセージ編集が再適用後も反映されませんでした。\n- Message: {self._message.id}\n- Label: {self._label}",
				description=f"{self._label}: メッセージ {self._message.id} の編集が反映されませんでした",
				source="message_writer",
				guild_id=self._guild_id,
			)
