import { ChevronLeft, ChevronRight, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

export type Tone = "slate" | "blue" | "green" | "amber" | "red";

const BADGE_TONE: Record<Tone, string> = {
	slate: "badge-ghost",
	blue: "badge-soft badge-info",
	green: "badge-soft badge-success",
	amber: "badge-soft badge-warning",
	red: "badge-soft badge-error",
};

const LED_TONE: Record<Tone, string> = {
	slate: "bg-base-content/25",
	blue: "bg-info",
	green: "bg-success",
	amber: "bg-accent",
	red: "bg-error",
};

const STAT_TONE: Record<Tone, string> = {
	slate: "text-base-content",
	blue: "text-primary",
	green: "text-success",
	amber: "text-accent",
	red: "text-error",
};

export function Badge({ tone = "slate", children, className = "" }: { tone?: Tone; children: ReactNode; className?: string }) {
	return <span className={`badge badge-sm whitespace-nowrap ${BADGE_TONE[tone]} ${className}`}>{children}</span>;
}

export function Led({ tone = "slate", blink = false }: { tone?: Tone; blink?: boolean }) {
	return <span aria-hidden className={`inline-block size-2 shrink-0 rounded-full ${LED_TONE[tone]} ${blink ? "led-blink" : ""}`} />;
}

/** 再生中を示すイコライザーバー */
export function EqualizerBars({ className = "" }: { className?: string }) {
	return (
		<span aria-hidden className={`flex h-3 items-end gap-[2px] ${className}`}>
			{[0, 1, 2, 3].map((index) => (
				<span key={index} className="eq-bar h-full w-[3px] flex-1 bg-accent" style={{ animationDelay: `${index * 0.18}s` }} />
			))}
		</span>
	);
}

/** 問題数ぶんのセグメント LED メーター (現在の問題位置を点滅させる) */
export function SegmentMeter({ total, current, className = "" }: { total: number; current: number; className?: string }) {
	const count = Math.max(0, Math.min(total, 50));
	if (count === 0) {
		return null;
	}
	return (
		<div role="img" aria-label={`問題 ${current} / ${total}`} className={`flex items-end gap-[3px] ${className}`}>
			{Array.from({ length: count }, (_, index) => {
				const position = index + 1;
				const style = position < current ? "bg-primary" : position === current ? "led-blink bg-accent" : "bg-base-300";
				return <span key={position} className={`h-3.5 flex-1 rounded-[2px] ${style}`} />;
			})}
		</div>
	);
}

export function Panel({
	title,
	action,
	children,
	className = "",
	bodyClassName = "",
}: {
	title?: ReactNode;
	action?: ReactNode;
	children: ReactNode;
	className?: string;
	bodyClassName?: string;
}) {
	return (
		<section className={`overflow-hidden rounded-box border border-base-300 bg-base-200 ${className}`}>
			{(title || action) && (
				<header className="flex min-h-11 flex-wrap items-center justify-between gap-2 border-b border-base-300 px-4 py-2">
					{title && <h2 className="font-display font-bold text-sm tracking-wide text-base-content/70">{title}</h2>}
					{action}
				</header>
			)}
			<div className={`p-4 ${bodyClassName}`}>{children}</div>
		</section>
	);
}

export function StatCard({ label, value, sub, tone = "slate" }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone }) {
	return (
		<div className="rounded-box border border-base-300 bg-base-200 px-4 py-3">
			<p className="font-mono text-[10px] tracking-[0.2em] text-base-content/45 uppercase">{label}</p>
			<p className={`mt-2 font-display font-bold text-3xl leading-none tracking-wide ${STAT_TONE[tone]}`}>{value}</p>
			{sub !== undefined && <p className="mt-2 text-xs text-base-content/50">{sub}</p>}
		</div>
	);
}

export function PageHeader({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
	return (
		<div className="mb-5 flex flex-wrap items-end justify-between gap-3">
			<div className="min-w-0">
				<h1 className="font-display font-bold text-2xl tracking-wide text-base-content">{title}</h1>
				{description !== undefined && <p className="mt-1 text-sm text-base-content/50">{description}</p>}
			</div>
			{action}
		</div>
	);
}

export function Loading() {
	return (
		<div className="space-y-3" aria-busy="true" aria-live="polite">
			<div className="skeleton h-24 w-full rounded-box" />
			<div className="skeleton h-64 w-full rounded-box" />
		</div>
	);
}

export function ErrorNotice({ error }: { error: unknown }) {
	const message = error instanceof Error ? error.message : String(error);
	return (
		<div role="alert" className="alert alert-error alert-soft mb-4">
			<TriangleAlert className="size-4" />
			<span className="text-sm">読み込みに失敗しました: {message}</span>
		</div>
	);
}

export function EmptyState({ title = "データがありません", hint }: { title?: string; hint?: string }) {
	return (
		<div className="flex flex-col items-center gap-1 py-10 text-center">
			<p className="font-display font-bold text-sm text-base-content/60">{title}</p>
			{hint && <p className="text-xs text-base-content/40">{hint}</p>}
		</div>
	);
}

export function Pagination({
	total,
	limit,
	offset,
	onChange,
}: {
	total: number;
	limit: number;
	offset: number;
	onChange: (offset: number) => void;
}) {
	if (total <= limit) {
		return null;
	}
	const page = Math.floor(offset / limit) + 1;
	const pages = Math.ceil(total / limit);
	return (
		<div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-base-content/50">
			<span className="font-mono">
				{offset + 1}–{Math.min(offset + limit, total)} / {total.toLocaleString("ja-JP")} 件
			</span>
			<div className="flex items-center gap-3">
				<span className="font-mono">
					{page} / {pages}
				</span>
				<div className="join">
					<button
						type="button"
						className="btn btn-sm join-item"
						aria-label="前のページ"
						disabled={offset === 0}
						onClick={() => onChange(Math.max(0, offset - limit))}
					>
						<ChevronLeft className="size-4" />
					</button>
					<button
						type="button"
						className="btn btn-sm join-item"
						aria-label="次のページ"
						disabled={offset + limit >= total}
						onClick={() => onChange(offset + limit)}
					>
						<ChevronRight className="size-4" />
					</button>
				</div>
			</div>
		</div>
	);
}

export const TABLE_CLASS = "table table-zebra table-sm w-full";
export const MONO_CELL = "font-mono text-xs";
