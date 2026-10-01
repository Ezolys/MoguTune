import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api";
import { Badge, ErrorNotice, Led, Loading, PageHeader, Panel } from "../components/ui";
import { formatDateTime } from "../format";

export function Maintenance() {
	const queryClient = useQueryClient();
	const query = useQuery({ queryKey: ["maintenance"], queryFn: api.maintenance });
	const [enabled, setEnabled] = useState(false);
	const [message, setMessage] = useState("");

	useEffect(() => {
		if (query.data) {
			setEnabled(query.data.enabled);
			setMessage(query.data.message ?? "");
		}
	}, [query.data]);

	const mutation = useMutation({
		mutationFn: () => api.updateMaintenance(enabled, message.trim() === "" ? null : message.trim()),
		onSuccess: (data) => {
			queryClient.setQueryData(["maintenance"], data);
		},
	});

	if (query.isLoading) {
		return <Loading />;
	}
	if (query.error) {
		return <ErrorNotice error={query.error} />;
	}

	const state = query.data;

	return (
		<>
			<PageHeader
				title="メンテナンス"
				description="メンテナンス中はすべてのサーバーでクイズを開始できなくなります"
				action={state?.enabled ? <Badge tone="red">メンテナンス中</Badge> : <Badge tone="green">通常稼働</Badge>}
			/>

			<div className="grid gap-4 lg:grid-cols-2">
				<Panel title="稼働モード">
					<div className="flex flex-wrap items-center justify-between gap-4">
						<div className="flex items-center gap-3">
							<Led tone={enabled ? "red" : "green"} blink={enabled} />
							<div>
								<p className="font-display font-bold text-lg tracking-wide">{enabled ? "メンテナンスモード" : "通常稼働"}</p>
								<p className="mt-0.5 text-xs text-base-content/50">
									{enabled ? "クイズの開始を停止しています" : "クイズを開始できます"}
								</p>
							</div>
						</div>
						<label className="flex cursor-pointer items-center gap-3">
							<span className="font-mono text-[10px] tracking-[0.2em] text-base-content/40 uppercase">{enabled ? "ON" : "OFF"}</span>
							<input
								type="checkbox"
								role="switch"
								aria-label="メンテナンスモード"
								className={`toggle toggle-lg ${enabled ? "toggle-error" : ""}`}
								checked={enabled}
								onChange={(event) => setEnabled(event.target.checked)}
							/>
						</label>
					</div>
					{state?.updated_at && (
						<p className="mt-4 border-t border-base-300 pt-3 font-mono text-[11px] text-base-content/40">
							最終更新 {formatDateTime(state.updated_at)}
							{state.updated_by ? ` / ${state.updated_by}` : ""}
						</p>
					)}
				</Panel>

				<Panel title="クイズ開始時に表示するメッセージ (任意)">
					<textarea
						className="textarea w-full leading-relaxed"
						rows={4}
						placeholder="未入力の場合は Bot の言語設定に応じた既定メッセージが表示されます"
						maxLength={1000}
						value={message}
						onChange={(event) => setMessage(event.target.value)}
					/>
					<p className="mt-1 text-right font-mono text-[10px] text-base-content/35">{message.length} / 1000</p>
				</Panel>
			</div>

			<div className="mt-4 flex flex-wrap items-center gap-3">
				<button type="button" className="btn btn-primary" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
					{mutation.isPending && <span className="loading loading-spinner loading-xs" />}
					変更を保存
				</button>
				{mutation.error && <span className="text-sm text-error">{mutation.error instanceof Error ? mutation.error.message : "保存に失敗しました"}</span>}
				{mutation.isSuccess && <span className="text-sm text-success">保存しました</span>}
			</div>

			<div className="mt-4">
				<Panel title="動作">
					<ul className="list-disc space-y-1 pl-5 text-sm text-base-content/60">
						<li>有効中は /play (コンテキストメニュー含む) がクイズを開始せず、メンテナンスメッセージを返します。</li>
						<li>実行中のクイズはそのまま継続され、/end で終了できます。</li>
						<li>設定は MongoDB の bot_state コレクションに保存され、Bot 再起動後も維持されます。</li>
						<li>Bot 側の /maintenance コマンド (オーナー専用) からも切り替えられます。</li>
					</ul>
				</Panel>
			</div>
		</>
	);
}
