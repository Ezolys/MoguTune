import type {
	ActiveQuizResponse,
	CommandLogsResponse,
	CommandSummary,
	ErrorDetail,
	ErrorsResponse,
	ErrorSummary,
	Guild,
	MaintenanceState,
	QuizHistoryResponse,
	QuizSummary,
	StatusResponse,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(`${BASE}${path}`, {
		headers: { "Content-Type": "application/json" },
		...init,
	});
	if (!response.ok) {
		const body = (await response.json().catch(() => null)) as { detail?: string } | null;
		throw new Error(body?.detail ?? `HTTP ${response.status}`);
	}
	return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
	const search = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value !== undefined && value !== "") {
			search.set(key, String(value));
		}
	}
	const text = search.toString();
	return text ? `?${text}` : "";
}

export const api = {
	me: () => request<{ email: string | null }>("/me"),
	status: () => request<StatusResponse>("/status"),
	guilds: () => request<Guild[]>("/guilds"),

	commandSummary: (days: number, guildId?: number) =>
		request<CommandSummary>(`/commands/summary${query({ days, guild_id: guildId })}`),
	commandLogs: (params: { limit: number; offset: number; guild_id?: number; command?: string; ok?: boolean; q?: string }) =>
		request<CommandLogsResponse>(`/commands/logs${query({ ...params })}`),
	commandFilters: () => request<{ commands: string[] }>("/commands/filters"),

	quizActive: () => request<ActiveQuizResponse>("/quiz/active"),
	quizHistory: (params: { limit: number; offset: number; guild_id?: number }) =>
		request<QuizHistoryResponse>(`/quiz/history${query({ ...params })}`),
	quizSummary: (days: number, guildId?: number) => request<QuizSummary>(`/quiz/summary${query({ days, guild_id: guildId })}`),

	errorSummary: (days: number) => request<ErrorSummary>(`/errors/summary${query({ days })}`),
	errors: (params: { limit: number; offset: number; source?: string; q?: string }) =>
		request<ErrorsResponse>(`/errors${query({ ...params })}`),
	errorDetail: (errorCode: string) => request<ErrorDetail>(`/errors/${encodeURIComponent(errorCode)}`),

	maintenance: () => request<MaintenanceState>("/maintenance"),
	updateMaintenance: (enabled: boolean, message: string | null) =>
		request<MaintenanceState>("/maintenance", { method: "PUT", body: JSON.stringify({ enabled, message }) }),
};
