import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { EmptyState, ErrorNotice, Loading, MONO_CELL, PageHeader, Panel, TABLE_CLASS } from "../components/ui";
import { formatDate, formatNumber } from "../format";

export function Guilds() {
	const query = useQuery({ queryKey: ["guilds"], queryFn: api.guilds });

	if (query.isLoading) {
		return <Loading />;
	}
	if (query.error) {
		return <ErrorNotice error={query.error} />;
	}

	const guilds = query.data ?? [];

	return (
		<>
			<PageHeader title="サーバー" description={`参加中のサーバー: ${formatNumber(guilds.length)} 件`} />
			<Panel title="参加サーバー">
				{guilds.length === 0 ? (
					<EmptyState title="サーバー情報がありません" />
				) : (
					<div className="overflow-x-auto">
						<table className={TABLE_CLASS}>
							<thead>
								<tr>
									<th>サーバー</th>
									<th>サーバーID</th>
									<th>メンバー数</th>
									<th>参加日</th>
								</tr>
							</thead>
							<tbody>
								{guilds.map((guild) => (
									<tr key={guild.guild_id}>
										<td>
											<div className="flex items-center gap-2">
												{guild.icon_url ? (
													<img src={guild.icon_url} alt="" className="size-6 rounded-full" />
												) : (
													<span className="grid size-6 place-items-center rounded-full bg-base-300 text-[10px] text-base-content/60">
														{guild.name.slice(0, 1)}
													</span>
												)}
												<span className="font-medium">{guild.name}</span>
											</div>
										</td>
										<td className={`${MONO_CELL} text-base-content/50`}>{guild.guild_id}</td>
										<td className={MONO_CELL}>{formatNumber(guild.member_count)}</td>
										<td className={`${MONO_CELL} text-base-content/50`}>{formatDate(guild.joined_at)}</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</Panel>
		</>
	);
}
