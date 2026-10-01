import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api";
import { AXIS_TICK, CHART, TOOLTIP_PROPS } from "../components/chart";
import { Badge, EmptyState, ErrorNotice, Loading, MONO_CELL, PageHeader, Pagination, Panel, StatCard, TABLE_CLASS } from "../components/ui";
import { formatDateTime, formatNumber, truncate } from "../format";

const LIMIT = 50;
const RANGES = [
	{ days: 7, label: "7日" },
	{ days: 30, label: "30日" },
	{ days: 90, label: "90日" },
];

export function Commands() {
	const [days, setDays] = useState(7);
	const [offset, setOffset] = useState(0);
	const [command, setCommand] = useState("");
	const [status, setStatus] = useState("");
	const [searchInput, setSearchInput] = useState("");
	const [search, setSearch] = useState("");

	const summaryQuery = useQuery({ queryKey: ["commands", "summary", days], queryFn: () => api.commandSummary(days) });
	const filtersQuery = useQuery({ queryKey: ["commands", "filters"], queryFn: api.commandFilters, staleTime: 300_000 });
	const logsQuery = useQuery({
		queryKey: ["commands", "logs", days, offset, command, status, search],
		queryFn: () =>
			api.commandLogs({
				limit: LIMIT,
				offset,
				command: command || undefined,
				ok: status === "" ? undefined : status === "ok",
				q: search || undefined,
			}),
	});

	const summary = summaryQuery.data;
	const logs = logsQuery.data;

	return (
		<>
			<PageHeader
				title="コマンド"
				description="実行回数と実行ログ"
				action={
					<div className="join">
						{RANGES.map((range) => (
							<button
								key={range.days}
								type="button"
								className={`btn btn-sm join-item ${days === range.days ? "btn-active" : ""}`}
								onClick={() => {
									setDays(range.days);
									setOffset(0);
								}}
							>
								{range.label}
							</button>
						))}
					</div>
				}
			/>

			{summaryQuery.error && <ErrorNotice error={summaryQuery.error} />}

			{summary && (
				<div className="mb-4 space-y-4">
					<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
						<StatCard label="Executions" value={formatNumber(summary.total)} sub={`直近 ${days} 日`} />
						<StatCard
							label="Success Rate"
							value={`${summary.success_rate}%`}
							tone={summary.success_rate >= 99 ? "green" : summary.success_rate >= 95 ? "amber" : "red"}
						/>
						<StatCard label="Errors" value={formatNumber(summary.errors)} tone={summary.errors > 0 ? "red" : "slate"} />
						<StatCard label="Commands" value={formatNumber(summary.by_command.length)} />
					</div>

					<div className="grid gap-4 lg:grid-cols-2">
						<Panel title="日別の実行回数">
							<div className="h-56">
								<ResponsiveContainer width="100%" height="100%">
									<AreaChart data={summary.by_day}>
										<defs>
											<linearGradient id="commandCount" x1="0" y1="0" x2="0" y2="1">
												<stop offset="5%" stopColor={CHART.primary} stopOpacity={0.45} />
												<stop offset="95%" stopColor={CHART.primary} stopOpacity={0} />
											</linearGradient>
										</defs>
										<CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
										<XAxis dataKey="date" tick={AXIS_TICK} minTickGap={28} tickFormatter={(value: string) => value.slice(5)} />
										<YAxis tick={AXIS_TICK} allowDecimals={false} width={32} />
										<Tooltip {...TOOLTIP_PROPS} />
										<Area type="monotone" dataKey="count" name="実行" stroke={CHART.primary} fill="url(#commandCount)" />
										<Area type="monotone" dataKey="errors" name="失敗" stroke={CHART.error} fillOpacity={0} />
									</AreaChart>
								</ResponsiveContainer>
							</div>
						</Panel>

						<Panel title="コマンド別 (上位10件)">
							{summary.by_command.length === 0 ? (
								<EmptyState />
							) : (
								<div className="h-56">
									<ResponsiveContainer width="100%" height="100%">
										<BarChart data={summary.by_command} layout="vertical" margin={{ left: 16 }}>
											<CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
											<XAxis type="number" tick={AXIS_TICK} allowDecimals={false} />
											<YAxis type="category" dataKey="command" tick={AXIS_TICK} width={110} />
											<Tooltip {...TOOLTIP_PROPS} />
											<Bar dataKey="count" name="実行" fill={CHART.primary} radius={[0, 4, 4, 0]} />
											<Bar dataKey="errors" name="失敗" fill={CHART.error} radius={[0, 4, 4, 0]} />
										</BarChart>
									</ResponsiveContainer>
								</div>
							)}
						</Panel>
					</div>
				</div>
			)}

			<Panel title="実行ログ">
				<div className="mb-3 flex flex-wrap items-center gap-2">
					<select
						className="select select-sm w-44"
						value={command}
						onChange={(event) => {
							setCommand(event.target.value);
							setOffset(0);
						}}
					>
						<option value="">すべてのコマンド</option>
						{(filtersQuery.data?.commands ?? []).map((name) => (
							<option key={name} value={name}>
								/{name}
							</option>
						))}
					</select>
					<select
						className="select select-sm w-36"
						value={status}
						onChange={(event) => {
							setStatus(event.target.value);
							setOffset(0);
						}}
					>
						<option value="">すべての結果</option>
						<option value="ok">成功</option>
						<option value="ng">失敗</option>
					</select>
					<label className="input input-sm w-52">
						<Search className="size-3.5 opacity-50" />
						<input
							placeholder="検索 (Enter)"
							value={searchInput}
							onChange={(event) => setSearchInput(event.target.value)}
							onKeyDown={(event) => {
								if (event.key === "Enter") {
									setSearch(searchInput);
									setOffset(0);
								}
							}}
						/>
					</label>
				</div>
				{logsQuery.isLoading ? (
					<Loading />
				) : logsQuery.error ? (
					<ErrorNotice error={logsQuery.error} />
				) : !logs || logs.items.length === 0 ? (
					<EmptyState title="実行ログがありません" hint="Bot がコマンドを使われると、ここに記録されます" />
				) : (
					<>
						<div className="overflow-x-auto">
							<table className={TABLE_CLASS}>
								<thead>
									<tr>
										<th>日時</th>
										<th>コマンド</th>
										<th>サーバー</th>
										<th>ユーザー</th>
										<th>結果</th>
										<th>オプション</th>
									</tr>
								</thead>
								<tbody>
									{logs.items.map((log, index) => (
										<tr key={`${log.created_at}-${index}`}>
											<td className={`${MONO_CELL} whitespace-nowrap text-base-content/50`}>{formatDateTime(log.created_at)}</td>
											<td className={`${MONO_CELL} text-primary`}>/{log.command}</td>
											<td>{log.guild_name ?? (log.guild_id ? String(log.guild_id) : "DM")}</td>
											<td className={`${MONO_CELL} text-base-content/50`}>{log.user_id ?? "-"}</td>
											<td>
												{log.ok ? (
													<Badge tone="green">成功</Badge>
												) : (
													<Badge tone={log.error_type === "internal" ? "red" : "amber"}>{log.error_type ?? "失敗"}</Badge>
												)}
											</td>
											<td className="max-w-xs truncate font-mono text-[11px] text-base-content/40" title={log.options.join(", ")}>
												{log.options.length > 0 ? truncate(log.options.join(", "), 60) : "-"}
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
						<Pagination total={logs.total} limit={LIMIT} offset={offset} onChange={setOffset} />
					</>
				)}
			</Panel>
		</>
	);
}
