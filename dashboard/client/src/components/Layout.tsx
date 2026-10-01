import { useQuery } from "@tanstack/react-query";
import { AudioLines, LayoutDashboard, Menu, Server, Terminal, TriangleAlert, Wrench } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { api } from "../api";
import { Led } from "./ui";

const NAV_ITEMS = [
	{ to: "/", label: "概要", icon: LayoutDashboard },
	{ to: "/commands", label: "コマンド", icon: Terminal },
	{ to: "/quiz", label: "クイズ", icon: AudioLines },
	{ to: "/errors", label: "エラー", icon: TriangleAlert },
	{ to: "/guilds", label: "サーバー", icon: Server },
	{ to: "/maintenance", label: "メンテナンス", icon: Wrench },
];

export function Layout() {
	const [drawerOpen, setDrawerOpen] = useState(false);
	const location = useLocation();
	const statusQuery = useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: 15_000 });
	const meQuery = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });

	const online = statusQuery.data?.online ?? false;
	const version = statusQuery.data?.status?.version;
	const currentLabel = NAV_ITEMS.find((item) => item.to === location.pathname)?.label ?? "";

	return (
		<div className="drawer lg:drawer-open">
			<input
				id="nav-drawer"
				type="checkbox"
				className="drawer-toggle"
				checked={drawerOpen}
				onChange={(event) => setDrawerOpen(event.target.checked)}
			/>
			<div className="drawer-content flex min-h-screen flex-col">
				<header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-base-300 bg-base-100/90 px-4 backdrop-blur">
					<label htmlFor="nav-drawer" className="btn btn-ghost btn-sm lg:hidden" aria-label="メニューを開く">
						<Menu className="size-5" />
					</label>
					<span className="font-display font-bold text-sm tracking-wide text-base-content/60">{currentLabel}</span>
					<div className="ml-auto flex items-center gap-3 text-xs">
						<span className="flex items-center gap-2">
							<Led tone={online ? "green" : "red"} blink={!online} />
							<span className="font-display font-bold tracking-wide">{online ? "オンライン" : "オフライン"}</span>
						</span>
						{version && <span className="hidden font-mono text-base-content/40 sm:inline">v{version}</span>}
						{meQuery.data?.email && (
							<span className="hidden max-w-40 truncate font-mono text-base-content/40 md:inline" title={meQuery.data.email}>
								{meQuery.data.email}
							</span>
						)}
					</div>
				</header>
				<main className="min-w-0 flex-1 p-4 lg:p-6">
					<Outlet />
				</main>
			</div>
			<div className="drawer-side z-40">
				<label htmlFor="nav-drawer" aria-label="メニューを閉じる" className="drawer-overlay" />
				<aside className="flex min-h-full w-64 flex-col border-r border-base-300 bg-base-200">
					<div className="flex items-center gap-3 px-4 py-4">
						<span className="grid size-9 place-items-center rounded-box bg-primary/15 text-primary">
							<AudioLines className="size-5" />
						</span>
						<div>
							<p className="font-display font-extrabold text-lg leading-none tracking-wide">MoguTune</p>
							<p className="mt-0.5 font-mono text-[9px] tracking-[0.25em] text-base-content/40 uppercase">Control Room</p>
						</div>
					</div>
					<ul className="menu w-full flex-1 gap-0.5 px-2 py-2">
						{NAV_ITEMS.map((item) => (
							<li key={item.to}>
								<NavLink
									to={item.to}
									end={item.to === "/"}
									onClick={() => setDrawerOpen(false)}
									className={({ isActive }) => `${isActive ? "nav-active" : ""} font-display font-bold tracking-wide`}
								>
									<item.icon className="size-4" />
									{item.label}
								</NavLink>
							</li>
						))}
					</ul>
					<div className="border-t border-base-300 px-4 py-3">
						<div className="flex items-center gap-2 text-xs text-base-content/50">
							<Led tone={online ? "green" : "red"} blink={!online} />
							<span className="font-display font-bold tracking-wide">{online ? "稼働中" : "停止中"}</span>
						</div>
						<p className="mt-1 font-mono text-[10px] text-base-content/35">MoguTune Dashboard</p>
					</div>
				</aside>
			</div>
		</div>
	);
}
