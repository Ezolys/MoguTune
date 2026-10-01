/** Recharts を DaisyUI テーマへ合わせるための共通スタイル */

export const CHART = {
	grid: "#262a35",
	axis: "#9ba3b4",
	primary: "#5b9bd5",
	accent: "#ffc94d",
	error: "#dd2e44",
	success: "#8cb05b",
} as const;

export const AXIS_TICK = { fill: CHART.axis, fontSize: 11, fontFamily: "IBM Plex Mono, monospace" };

export const TOOLTIP_PROPS = {
	contentStyle: {
		backgroundColor: "#1a1d25",
		border: "1px solid #262a35",
		borderRadius: 8,
		fontSize: 12,
		fontFamily: "IBM Plex Mono, monospace",
	},
	labelStyle: { color: CHART.axis },
	itemStyle: { color: "#e9ebf2" },
} as const;
