import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api";
import { AXIS_TICK, CHART, TOOLTIP_PROPS } from "../components/chart";
import { Badge, EmptyState, ErrorNotice, Loading, MONO_CELL, PageHeader, Pagination, Panel, StatCard, TABLE_CLASS } from "../components/ui";
import { formatDateTime, formatNumber, formatRelative, truncate } from "../format";

const LIMIT = 50;

export function Errors() {
	const [offset, setOffset] = useState(0);
	const [source, setSource] = useState("");
	const [selected, setSelected] = useState<string | null>(null);

	const summaryQuery = useQuery({ queryKey: ["errors", "summary", 30], queryFn: () => api.errorSummary(30) });
	const listQuery = useQuery({
		queryKey: ["errors", "list", offset, source],
		queryFn: () => api.errors({ limit: LIMIT, offset, source: source || undefined }),
	});
	const detailQuery = useQuery({
		queryKey: ["errors", "detail", selected],
		queryFn: () => api.errorDetail(selected ?? ""),
		enabled: selected !== null,
	});

	const summary = summaryQuery.data;
	const list = listQuery.data;

	return (
		<>
			<PageHeader title="エラー" description="内部エラーの発生状況 (直近30日)" />

			{summaryQuery.error && <ErrorNotice error={summaryQuery.error} />}

			{summary && (
				<div className="space-y-4">
					<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
						<StatCard label="Errors / 30d" value={formatNumber(summary.total)} tone={summary.total > 0 ? "red" : "slate"} />
						<StatCard label="Last 24h" value={formatNumber(summary.last_24h)} tone={summary.last_24h > 0 ? "red" : "green"} />
						<StatCard label="Signatures" value={formatNumber(summary.signatures.length)} />
						<StatCard label="Sources" value={formatNumber(summary.by_source.length)} />
					</div>

					<Panel title="日別の発生数">
						<div className="h-56">
							<ResponsiveContainer width="100%" height="100%">
								<AreaChart data={summary.by_day}>
									<defs>
										<linearGradient id="errorCount" x1="0" y1="0" x2="0" y2="1">
											<stop offset="5%" stopColor={CHART.error} stopOpacity={0.45} />
											<stop offset="95%" stopColor={CHART.error} stopOpacity={0} />
										</linearGradient>
									</defs>
									<CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
									<XAxis dataKey="date" tick={AXIS_TICK} minTickGap={28} tickFormatter={(value: string) => value.slice(5)} />
									<YAxis tick={AXIS_TICK} allowDecimals={false} width={32} />
									<Tooltip {...TOOLTIP_PROPS} />
									<Area type="monotone" dataKey="count" name="発生数" stroke={CHART.error} fill="url(#errorCount)" />
								</AreaChart>
							</ResponsiveContainer>
						</div>
					</Panel>

					<div className="grid gap-4 lg:grid-cols-2">
						<Panel title="種類別 (トレースバックのシグネチャ)">
							{summary.signatures.length === 0 ? (
								<EmptyState title="エラーは記録されていません" hint="問題が起きると、ここにトレースバックとともに残ります" />
							) : (
								<ul className="space-y-2">
									{summary.signatures.map((signature) => (
										<li key={signature._id}>
											<button
												type="button"
												className="w-full rounded-box border border-base-300 bg-base-100/40 px-3 py-2 text-left transition-colors hover:border-error/40 hover:bg-base-100"
												onClick={() => setSelected(signature.error_code)}
											>
												<div className="flex items-center justify-between gap-2">
													<span className="truncate font-mono text-xs text-base-content/70">{signature.source || "(unknown)"}</span>
													<Badge tone="red">{signature.count} 回</Badge>
												</div>
												<p className="mt-1 truncate text-xs text-base-content/45">{truncate(signature.description || "-", 90)}</p>
												<p className="mt-1 font-mono text-[10px] text-base-content/35">最終発生: {formatRelative(signature.last_seen)}</p>
											</button>
										</li>
									))}
								</ul>
							)}
						</Panel>

						<Panel title="発生元別">
							{summary.by_source.length === 0 ? (
								<EmptyState />
							) : (
								<ul className="space-y-2">
									{summary.by_source.map((row) => (
										<li key={row.source} className="flex items-center justify-between gap-2 rounded-box border border-base-300 bg-base-100/40 px-3 py-2 text-sm">
											<span className="truncate font-mono text-xs text-base-content/70">{row.source}</span>
											<span className="font-display font-bold text-base-content/60">{formatNumber(row.count)}</span>
										</li>
									))}
								</ul>
							)}
						</Panel>
					</div>
				</div>
			)}

			<div className="mt-4">
				<Panel
					title="発生履歴"
					action={
						<select
							className="select select-sm"
							value={source}
							onChange={(event) => {
								setSource(event.target.value);
								setOffset(0);
							}}
						>
							<option value="">すべての発生元</option>
							{(summary?.by_source ?? []).map((row) => (
								<option key={row.source} value={row.source}>
									{row.source}
								</option>
							))}
						</select>
					}
				>
					{listQuery.isLoading ? (
						<Loading />
					) : listQuery.error ? (
						<ErrorNotice error={listQuery.error} />
					) : !list || list.items.length === 0 ? (
						<EmptyState title="発生履歴がありません" />
					) : (
						<>
							<div className="overflow-x-auto">
								<table className={TABLE_CLASS}>
									<thead>
										<tr>
											<th>日時</th>
											<th>発生元</th>
											<th>概要</th>
											<th>エラーコード</th>
										</tr>
									</thead>
									<tbody>
										{list.items.map((item) => (
											<tr key={item.error_code} className="cursor-pointer" onClick={() => setSelected(item.error_code)}>
												<td className={`${MONO_CELL} whitespace-nowrap text-base-content/50`}>{formatDateTime(item.created_at)}</td>
												<td className="font-mono text-xs text-base-content/70">{item.source || "-"}</td>
												<td className="max-w-md truncate text-xs text-base-content/45">{truncate(item.description || "-", 100)}</td>
												<td className={`${MONO_CELL} text-primary`}>{item.error_code.slice(0, 8)}…</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
							<Pagination total={list.total} limit={LIMIT} offset={offset} onChange={setOffset} />
						</>
					)}
				</Panel>
			</div>

			{selected !== null && (
				<div className="modal modal-open" role="dialog" aria-modal="true" aria-label="エラー詳細">
					<div className="modal-box max-w-3xl border border-base-300">
						<div className="flex items-start justify-between gap-4">
							<div className="min-w-0">
								<h2 className="font-display font-bold text-lg tracking-wide">エラー詳細</h2>
								{detailQuery.data && (
									<p className="mt-1 font-mono text-[11px] text-base-content/45">
										{formatDateTime(detailQuery.data.created_at)} ・ {detailQuery.data.source || "(unknown)"}
									</p>
								)}
							</div>
							<button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>
								<X className="size-4" />
								閉じる
							</button>
						</div>

						{detailQuery.isLoading ? (
							<Loading />
						) : detailQuery.error ? (
							<ErrorNotice error={detailQuery.error} />
						) : detailQuery.data ? (
							<div className="mt-4 space-y-3">
								<div className="flex flex-wrap gap-2">
									<Badge tone="slate">CODE {detailQuery.data.error_code.slice(0, 8)}…</Badge>
									{detailQuery.data.command && <Badge tone="blue">/{detailQuery.data.command}</Badge>}
									{detailQuery.data.guild_id && <Badge tone="slate">Guild {detailQuery.data.guild_id}</Badge>}
									{detailQuery.data.user_id && <Badge tone="slate">User {detailQuery.data.user_id}</Badge>}
								</div>
								{detailQuery.data.description && (
									<pre className="max-h-40 overflow-auto rounded-box border border-base-300 bg-base-100 p-3 font-mono text-[11px] whitespace-pre-wrap text-base-content/70">
										{detailQuery.data.description}
									</pre>
								)}
								<pre className="max-h-96 overflow-auto rounded-box border border-error/30 bg-base-100 p-3 font-mono text-[11px] whitespace-pre-wrap text-error/90">
									{detailQuery.data.traceback || "(トレースバックなし)"}
								</pre>
							</div>
						) : null}
					</div>
					<button type="button" className="modal-backdrop" aria-label="閉じる" onClick={() => setSelected(null)}>
						close
					</button>
				</div>
			)}
		</>
	);
}
