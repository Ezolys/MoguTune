export interface LavalinkNode {
	id: string;
	connected: boolean;
	connecting: boolean;
	players: number | null;
	playing_players: number | null;
}

export type QuizPhase = "preparing" | "answering" | "playing";

export interface ActiveSession {
	guild_id: number;
	guild_name: string | null;
	channel_id: number;
	voice_channel_name: string | null;
	owner_id: number | null;
	query: string;
	question_index: number;
	question_total: number;
	participants: number;
	phase: QuizPhase;
	started_at: string | null;
}

export interface BotStatus {
	version: string;
	commit: string;
	latency_ms: number;
	guild_count: number;
	user_count: number;
	active_sessions: ActiveSession[];
	lavalink: LavalinkNode[];
	started_at: string;
	updated_at: string;
}

export interface StatusResponse {
	online: boolean;
	status: BotStatus | null;
}

export interface Guild {
	guild_id: number;
	name: string;
	member_count: number;
	icon_url: string | null;
	joined_at: string | null;
	updated_at: string;
}

export interface DailyPoint {
	date: string;
	count: number;
	errors?: number;
	participants?: number;
}

export interface CommandSummary {
	total: number;
	errors: number;
	success_rate: number;
	by_command: { command: string; count: number; errors: number }[];
	by_day: DailyPoint[];
	by_guild: { guild_id: number; guild_name: string | null; count: number }[];
}

export interface CommandLog {
	command: string;
	ok: boolean;
	guild_id: number | null;
	guild_name: string | null;
	channel_id: number | null;
	user_id: number | null;
	options: string[];
	error_type: string | null;
	error_code: string | null;
	created_at: string;
}

export interface CommandLogsResponse {
	items: CommandLog[];
	total: number;
}

export interface QuizHistoryItem {
	guild_id: number;
	guild_name: string | null;
	channel_id: number | null;
	voice_channel_name: string | null;
	owner_id: number | null;
	query: string;
	question_total: number;
	completed_questions: number;
	participants: number[];
	correct_counts: Record<string, number>;
	started_at: string | null;
	ended_at: string;
}

export interface QuizHistoryResponse {
	items: QuizHistoryItem[];
	total: number;
}

export interface QuizSummary {
	total: number;
	completed: number;
	participants: number;
	by_day: DailyPoint[];
}

export interface ActiveQuizResponse {
	sessions: ActiveSession[];
	updated_at: string | null;
}

export interface ErrorSignature {
	_id: string;
	count: number;
	source: string;
	description: string;
	error_code: string;
	last_seen: string;
}

export interface ErrorSummary {
	total: number;
	last_24h: number;
	by_day: DailyPoint[];
	by_source: { source: string; count: number }[];
	signatures: ErrorSignature[];
}

export interface ErrorItem {
	error_code: string;
	source: string;
	description: string;
	traceback_hash: string;
	guild_id: number | null;
	user_id: number | null;
	command: string | null;
	created_at: string;
}

export interface ErrorDetail extends ErrorItem {
	traceback: string;
}

export interface ErrorsResponse {
	items: ErrorItem[];
	total: number;
}

export interface MaintenanceState {
	enabled: boolean;
	message: string | null;
	updated_by: string | null;
	updated_at: string | null;
}
