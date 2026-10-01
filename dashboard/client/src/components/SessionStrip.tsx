import { EqualizerBars, Badge, Led, SegmentMeter, type Tone } from "./ui";
import { formatRelative, truncate } from "../format";
import type { ActiveSession, QuizPhase } from "../types";

const PHASE_LABELS: Record<QuizPhase, string> = {
	preparing: "準備中",
	playing: "再生中",
	answering: "解答受付中",
};

const PHASE_TONES: Record<QuizPhase, Tone> = {
	preparing: "blue",
	playing: "blue",
	answering: "amber",
};

/** 実行中クイズをミキサーのチャンネルに見立てたストリップ */
export function SessionStrip({ session }: { session: ActiveSession }) {
	const playing = session.phase !== "preparing";
	return (
		<article className="rounded-box border border-base-300 bg-base-100/50 p-3">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="flex min-w-0 items-center gap-2">
					{playing ? <EqualizerBars /> : <Led tone="blue" blink />}
					<span className="truncate font-display font-bold tracking-wide">{session.guild_name ?? session.guild_id}</span>
					<span className="truncate text-xs text-base-content/40">{session.voice_channel_name ?? session.channel_id}</span>
				</div>
				<Badge tone={PHASE_TONES[session.phase]}>{PHASE_LABELS[session.phase]}</Badge>
			</div>
			<SegmentMeter total={session.question_total} current={session.question_index} className="mt-3" />
			<div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-base-content/50">
				<span className="font-mono">
					{session.question_index} / {session.question_total || "-"} 問
				</span>
				<span>参加 {session.participants} 人</span>
				<span>開始 {formatRelative(session.started_at)}</span>
			</div>
			<p className="mt-1 truncate font-mono text-[11px] text-base-content/35" title={session.query}>
				{truncate(session.query, 70)}
			</p>
		</article>
	);
}
