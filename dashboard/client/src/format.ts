export function formatDateTime(value: string | null | undefined): string {
	if (!value) {
		return "-";
	}
	return new Date(value).toLocaleString("ja-JP", { hour12: false });
}

export function formatDate(value: string | null | undefined): string {
	if (!value) {
		return "-";
	}
	return new Date(value).toLocaleDateString("ja-JP");
}

export function formatNumber(value: number | null | undefined): string {
	if (value === null || value === undefined) {
		return "-";
	}
	return value.toLocaleString("ja-JP");
}

export function formatUptime(startedAt: string | null | undefined): string {
	if (!startedAt) {
		return "-";
	}
	const seconds = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
	const days = Math.floor(seconds / 86400);
	const hours = Math.floor((seconds % 86400) / 3600);
	const minutes = Math.floor((seconds % 3600) / 60);
	if (days > 0) {
		return `${days}日 ${hours}時間`;
	}
	if (hours > 0) {
		return `${hours}時間 ${minutes}分`;
	}
	return `${minutes}分`;
}

export function formatRelative(value: string | null | undefined): string {
	if (!value) {
		return "-";
	}
	const diff = Date.now() - new Date(value).getTime();
	const seconds = Math.floor(diff / 1000);
	if (seconds < 60) {
		return `${Math.max(0, seconds)}秒前`;
	}
	const minutes = Math.floor(seconds / 60);
	if (minutes < 60) {
		return `${minutes}分前`;
	}
	const hours = Math.floor(minutes / 60);
	if (hours < 24) {
		return `${hours}時間前`;
	}
	return `${Math.floor(hours / 24)}日前`;
}

export function truncate(value: string, max = 80): string {
	return value.length > max ? `${value.slice(0, max)}…` : value;
}
