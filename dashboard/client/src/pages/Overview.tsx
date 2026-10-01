import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { SessionStrip } from "../components/SessionStrip";
import { Badge, EmptyState, ErrorNotice, EqualizerBars, Led, Loading, PageHeader, Panel, StatCard } from "../components/ui";
import { formatNumber, formatRelative, formatUptime } from "../format";

export function Overview() {
	const query = useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: 15_000 });

	if (query.isLoading) {
		return <Loading />;
	}
	if (query.error) {
		return <ErrorNotice error={query.error} />;
	}

	const online = query.data?.online ?? false;
	const status = query.data?.status;

	return (
		<>
			<PageHeader
				title="概要"
				description={status ? `最終更新: ${formatRelative(status.updated_at)}` : "Bot の稼働状況"}
				action={
					<span className="flex items-center gap-2">
						<Led tone={online ? "green" : "red"} blink={!online} />
						<Badge tone={online ? "green" : "red"}>{online ? "オンライン" : "オフライン"}</Badge>
					</span>
				}
			/>

			{!status ? (
				<Panel>
					<EmptyState title="稼働状況がまだ記録されていません" hint="Bot が起動すると、ここに状態が表示されます" />
				</Panel>
			) : (
				<div className="space-y-4">
					<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
						<StatCard label="Servers" value={formatNumber(status.guild_count)} />
						<StatCard label="Users" value={formatNumber(status.user_count)} />
						<StatCard
							label="Live Quizzes"
							value={formatNumber(status.active_sessions.length)}
							tone={status.active_sessions.length > 0 ? "blue" : "slate"}
						/>
						<StatCard label="Latency" value={`${formatNumber(status.latency_ms)}ms`} tone={status.latency_ms < 200 ? "green" : "amber"} />
					</div>

					<Panel
						title="LIVE CHANNELS"
						bodyClassName="p-3 sm:p-4"
						action={
							status.active_sessions.length > 0 ? (
								<span className="flex items-center gap-2">
									<EqualizerBars />
									<span className="font-mono text-[10px] tracking-[0.2em] text-base-content/40">{status.active_sessions.length} ACTIVE</span>
								</span>
							) : null
						}
					>
						{status.active_sessions.length === 0 ? (
							<EmptyState title="実行中のクイズはありません" hint="/play でクイズが始まると、ここにリアルタイムで表示されます" />
						) : (
							<div className="grid grid-cols-1 gap-2 md:grid-cols-2 2xl:grid-cols-3">
								{status.active_sessions.map((session) => (
									<SessionStrip key={session.guild_id} session={session} />
								))}
							</div>
						)}
					</Panel>

					<div className="grid gap-4 lg:grid-cols-2">
						<Panel title="LAVALINK NODES">
							{status.lavalink.length === 0 ? (
								<EmptyState title="ノードが登録されていません" />
							) : (
								<ul className="space-y-2">
									{status.lavalink.map((node) => (
										<li key={node.id} className="flex flex-wrap items-center justify-between gap-2 rounded-box border border-base-300 bg-base-100/50 px-3 py-2 text-sm">
											<div className="flex items-center gap-2">
												<Led
													tone={node.connected ? "green" : node.connecting ? "amber" : "red"}
													blink={node.connecting}
												/>
												<span className="font-display font-bold tracking-wide">{node.id}</span>
												<Badge tone={node.connected ? "green" : node.connecting ? "amber" : "red"}>
													{node.connected ? "接続中" : node.connecting ? "接続処理中" : "未接続"}
												</Badge>
											</div>
											<span className="font-mono text-xs text-base-content/45">
												PLAY {node.playing_players ?? "-"} / CONN {node.players ?? "-"}
											</span>
										</li>
									))}
								</ul>
							)}
						</Panel>

						<Panel title="BOT">
							<dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
								<div>
									<dt className="font-mono text-[10px] tracking-[0.2em] text-base-content/40 uppercase">Version</dt>
									<dd className="mt-0.5 font-display font-bold tracking-wide">v{status.version}</dd>
								</div>
								<div>
									<dt className="font-mono text-[10px] tracking-[0.2em] text-base-content/40 uppercase">Commit</dt>
									<dd className="mt-0.5 font-mono text-xs">{status.commit}</dd>
								</div>
								<div>
									<dt className="font-mono text-[10px] tracking-[0.2em] text-base-content/40 uppercase">Uptime</dt>
									<dd className="mt-0.5 font-display font-bold tracking-wide">{formatUptime(status.started_at)}</dd>
								</div>
								<div>
									<dt className="font-mono text-[10px] tracking-[0.2em] text-base-content/40 uppercase">Started</dt>
									<dd className="mt-0.5 text-xs text-base-content/60">{formatRelative(status.started_at)}</dd>
								</div>
							</dl>
						</Panel>
					</div>
				</div>
			)}
		</>
	);
}
