import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api";
import { AXIS_TICK, CHART, TOOLTIP_PROPS } from "../components/chart";
import { SessionStrip } from "../components/SessionStrip";
import { EmptyState, ErrorNotice, Loading, MONO_CELL, PageHeader, Pagination, Panel, StatCard, TABLE_CLASS } from "../components/ui";
import { formatDateTime, formatNumber, truncate } from "../format";

const LIMIT = 50;

export function Quiz() {
	const [offset, setOffset] = useState(0);

	const activeQuery = useQuery({ queryKey: ["quiz", "active"], queryFn: api.quizActive, refetchInterval: 15_000 });
	const summaryQuery = useQuery({ queryKey: ["quiz", "summary", 30], queryFn: () => api.quizSummary(30) });
	const historyQuery = useQuery({ queryKey: ["quiz", "history", offset], queryFn: () => api.quizHistory({ limit: LIMIT, offset }) });

	const sessions = activeQuery.data?.sessions ?? [];
	const summary = summaryQuery.data;
	const history = historyQuery.data;

	return (
		<>
			<PageHeader title="クイズ" description="実行中のセッションと実施履歴" />

			<Panel title="LIVE CHANNELS" action={<span className="font-mono text-[10px] tracking-[0.2em] text-base-content/40">{sessions.length} ACTIVE</span>}>
				{activeQuery.isLoading ? (
					<Loading />
				) : activeQuery.error ? (
					<ErrorNotice error={activeQuery.error} />
				) : sessions.length === 0 ? (
					<EmptyState title="実行中のクイズはありません" hint="/play でクイズが始まると、ここにリアルタイムで表示されます" />
				) : (
					<div className="grid gap-3 xl:grid-cols-2">
						{sessions.map((session) => (
							<SessionStrip key={session.guild_id} session={session} />
						))}
					</div>
				)}
			</Panel>

			{summaryQuery.error && <ErrorNotice error={summaryQuery.error} />}

			{summary && (
				<div className="mt-4 space-y-4">
					<div className="grid grid-cols-3 gap-3">
						<StatCard label="Quizzes / 30d" value={formatNumber(summary.total)} />
						<StatCard label="Completed" value={formatNumber(summary.completed)} tone="green" />
						<StatCard label="Participants" value={formatNumber(summary.participants)} />
					</div>
					<Panel title="日別の実施回数 (30日)">
						<div className="h-56">
							<ResponsiveContainer width="100%" height="100%">
								<BarChart data={summary.by_day}>
									<CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
									<XAxis dataKey="date" tick={AXIS_TICK} minTickGap={28} tickFormatter={(value: string) => value.slice(5)} />
									<YAxis tick={AXIS_TICK} allowDecimals={false} width={32} />
									<Tooltip {...TOOLTIP_PROPS} />
									<Bar dataKey="count" name="クイズ" fill={CHART.primary} radius={[4, 4, 0, 0]} />
								</BarChart>
							</ResponsiveContainer>
						</div>
					</Panel>
				</div>
			)}

			<div className="mt-4">
				<Panel title="実施履歴">
					{historyQuery.isLoading ? (
						<Loading />
					) : historyQuery.error ? (
						<ErrorNotice error={historyQuery.error} />
					) : !history || history.items.length === 0 ? (
						<EmptyState title="クイズの履歴がありません" hint="クイズが終了すると、結果がここに残ります" />
					) : (
						<>
							<div className="overflow-x-auto">
								<table className={TABLE_CLASS}>
									<thead>
										<tr>
											<th>終了日時</th>
											<th>サーバー</th>
											<th>VC</th>
											<th>クエリ</th>
											<th>問題</th>
											<th>参加者</th>
										</tr>
									</thead>
									<tbody>
										{history.items.map((item, index) => (
											<tr key={`${item.ended_at}-${index}`}>
												<td className={`${MONO_CELL} whitespace-nowrap text-base-content/50`}>{formatDateTime(item.ended_at)}</td>
												<td>{item.guild_name ?? item.guild_id}</td>
												<td className="text-base-content/60">{item.voice_channel_name ?? "-"}</td>
												<td className="max-w-xs truncate font-mono text-[11px] text-base-content/40" title={item.query}>
													{truncate(item.query, 50)}
												</td>
												<td className={MONO_CELL}>
													{item.completed_questions} / {item.question_total}
												</td>
												<td className={MONO_CELL}>{item.participants.length}</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
							<Pagination total={history.total} limit={LIMIT} offset={offset} onChange={setOffset} />
						</>
					)}
				</Panel>
			</div>
		</>
	);
}
