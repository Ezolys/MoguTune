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
		<article className="rounded-box border border-base-300 bg-base-100/50 px-3 py-2">
			<div className="flex min-w-0 items-center gap-2">
				{playing ? <EqualizerBars /> : <Led tone="blue" blink />}
				<span className="min-w-0 truncate font-display font-bold text-sm tracking-wide">{session.guild_name ?? session.guild_id}</span>
				<span className="hidden min-w-0 truncate text-xs text-base-content/40 sm:inline">
					{session.voice_channel_name ?? session.channel_id}
				</span>
				<Badge tone={PHASE_TONES[session.phase]} className="ml-auto shrink-0">
					{PHASE_LABELS[session.phase]}
				</Badge>
			</div>
			<SegmentMeter total={session.question_total} current={session.question_index} className="mt-1.5" />
			<div className="mt-1.5 flex min-w-0 items-center gap-x-2.5 text-[11px] text-base-content/50 sm:gap-x-3">
				<span className="shrink-0 font-mono">
					{session.question_index} / {session.question_total || "-"} 問
				</span>
				<span className="shrink-0">参加 {session.participants} 人</span>
				<span className="shrink-0">開始 {formatRelative(session.started_at)}</span>
				<span className="min-w-0 flex-1 truncate text-right font-mono text-base-content/35" title={session.query}>
					{truncate(session.query, 70)}
				</span>
			</div>
		</article>
	);
}
