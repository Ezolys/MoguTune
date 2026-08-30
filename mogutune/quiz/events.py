import json
import logging
import traceback

import discord
import mafic
from mogutune_core.roster import RemoveReason

from mogutune.client import client
from mogutune.quiz.manager import quiz_session_manager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# ボイスチャンネルステータス変更時 (参加/退出等) イベント
@client.listen()
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
	session = quiz_session_manager.get_session(member.guild.id)
	# 対象のサーバーでクイズが行われている場合はメンバーのチェックを実行する
	if session is None:
		return

	# クイズが行われているボイスチャンネルに参加した
	if after.channel is not None and after.channel.id == session.channel_id:
		# 自分自身とボットは除外
		if member.id == client.user.id or member.bot:
			return
		# 参加待ちの列へ追加する
		await session.add_queue(member.id)

	# クイズが行われているボイスチャンネルから退出した
	elif before.channel is not None and after.channel is None and before.channel.id == session.channel_id:
		# 自分が退出した場合はクイズを終了する
		if member.id == client.user.id:
			await quiz_session_manager.end_session(member.guild.id)
			return
		# プレイヤーを削除する 場合によってはクイズ終了
		result = await session.remove_player(member.id)
		if result == RemoveReason.NO_PLAYERS_LEFT:
			logger.debug("- プレイヤー数0人: クイズ終了")
			await session.end()
		elif result == RemoveReason.OWNER_LEFT:
			logger.debug("- オーナー退出: クイズ終了")
			await session.end()
		await session.remove_queue(member.id)


# トラック再生例外イベント
@client.listen()
async def on_track_exception(event: mafic.TrackExceptionEvent) -> None:
	assert isinstance(event.player, mafic.Player)
	guild_id = event.player.guild.id
	logger.error("トラック再生例外: %s", event.exception)
	session = quiz_session_manager.get_session(guild_id)
	if session is None:
		return

	# SFX再生中の例外は待機を解放して復帰を試みる
	if session.is_playing_sfx:
		logger.warning("SFXの再生に失敗しました: %s", json.dumps(event.exception))
		if session.restore_track_after_sfx and session.original_track_before_sfx:
			try:
				await session.pl.play(
					session.original_track_before_sfx,
					start_time=session.original_position_before_sfx,
					volume=session.PL_VOLUME,
				)
				if not session.was_playing_before_sfx:
					await session.pl.pause()
			except Exception:
				logger.error("SFX例外後の楽曲復帰に失敗しました")
				logger.error(traceback.format_exc())
		session.SFX_FINISHED.set()
		return

	if not session.is_question_track_exception_target(event.track):
		return

	logger.warning("問題の再生に失敗したためスキップします: %s", session.format_track_title(event.track))
	logger.warning("例外: %s", json.dumps(event.exception))
	await session.skip_current_q_by_track_exception(event.track)


# 再生開始時イベント
@client.listen()
async def on_track_start(event: mafic.TrackEndEvent):
	assert isinstance(event.player, mafic.Player)
	guild_id = event.player.guild.id
	logger.debug(f"再生開始イベント: {guild_id}")


# 再生終了時イベント
@client.listen()
async def on_track_end(event: mafic.TrackEndEvent):
	assert isinstance(event.player, mafic.Player)
	guild_id = event.player.guild.id
	logger.debug(f"再生終了イベント: {guild_id} ({event.reason})")
	session = quiz_session_manager.get_session(guild_id)
	if session is None:
		return

	# SFXの再生が終了した場合
	if session.is_playing_sfx:
		logger.debug(f"SFX再生終了イベント: {guild_id}")
		# REPLACED の場合は無視する (original_track の有無に関わらず)
		if event.reason == mafic.EndReason.REPLACED:
			logger.debug("- REPLACEDのため無視")
			return
		# 元の楽曲の再生を再開
		if session.restore_track_after_sfx and session.original_track_before_sfx:
			try:
				# 元の楽曲を復帰
				await session.pl.play(
					session.original_track_before_sfx,
					start_time=session.original_position_before_sfx,
					volume=session.PL_VOLUME,
				)

				# SFX再生前に一時停止していた場合は一時停止状態に戻す
				if not session.was_playing_before_sfx:
					logger.debug("- SFX再生前は一時停止中だったため、一時停止状態に戻します")
					await session.pl.pause()
			except Exception:
				logger.error("SFX終了後の楽曲復帰に失敗しました")
				logger.error(traceback.format_exc())
		else:
			logger.debug("- SFX再生後の楽曲復帰は行いません")

		session.SFX_FINISHED.set()
		return

	# クイズの楽曲が終了した場合、次の問題へ進む
	# 誰も正解しないまま再生が終わった場合は正解情報を送信してサビを再生する（スキップと同様）
	if event.reason == mafic.EndReason.FINISHED:
		if session.can_answered:
			await session.reveal_answer_on_timeout(event.track)
		else:
			session.NEXT.set()
