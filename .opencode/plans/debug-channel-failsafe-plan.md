# Debugチャンネル道連れ問題 修正プラン

作成日: 2026-09-04
対象ブランチ: `feature/sonolink-migration`（`dev` へも適用可・SonoLink 非依存）
関連: `/play` 失敗調査（Lavalink `volume` 400問題の二次被害）

## 背景・故障連鎖の分析（ログの再構成）

1. 真因はVC接続失敗（Lavalink側 `volume` フィルター無効による400）だが、ユーザーへの通知が以下の順で全滅した
2. `prepare.py` の接続失敗分岐内 `msg.edit` が `RuntimeError: Session is closed`（Discord接続断ち・Bot停止中）で**元エラーを上書き**
3. 外側 `except` → `report_internal_error` → `debug_channel.send` も同一理由で失敗。「失敗時は空文字を返す」設計のため**エラーコード喪失＋トレースバックはローカルログにも残らず**（"内部エラー報告失敗" のみ記録）
4. フォールバックの `inter.channel.send` も失敗 → "Internal Error Message Send Failed" で終了。結果、**障害の記録がどこにも残らない**

設計上の欠陥は3点：①報告関数自体がDiscord依存で失敗時に診断情報を捨てる、②エラー通知系の `msg.edit`/`channel.send` が無防備で元例外をマスクする、③シャットダウン時の `CancelledError` と通常エラーの区別がない。

## Phase 1 — `DebugLogger.report_internal_error` の強化（核心）

- 送信前に接続ガード：メソッド内で `from mogutune.client import client` を遅延import（`client.py` が本モジュールをimportしているためトップレベル不可）し、`client.is_closed()` が真なら送信をスキップ
- `error_code` 生成を try の外へ移動し**常に非空コードを返す**（呼び出し側の空文字分岐は温存で互換性維持）
- 送信失敗時は元の `traceback_text`＋`description`＋コードを `logger.error` でローカルログ（ローテーション済み `logs/app.log`）へ出力。情報欠落をゼロにする
- 変更ファイル：`mogutune/debug_logger.py` のみ。ロケール・呼び出し側の変更不要

## Phase 2 — Discord送信ヘルパーの新設と適用

- 新規 `mogutune/discord_io.py` に `safe_edit(msg, ...)` / `safe_send(channel, ...)` を追加。`RuntimeError`（Session closed）・`aiohttp.ClientConnectionError`・`discord.HTTPException`/`NotFound`/`Forbidden` を捕捉して真偽値で返し、元例外をマスクしない
- 適用箇所：`prepare.py` のエラー通知系 `msg.edit`（接続失敗分岐）・`inter.channel.send`、`client.py` の `on_application_command_error` 内 `ctx.respond` 群。`session.py:_send_to_vc` は既に同等構造のため対象外（Phase 1の恩恵のみ受ける）
- 新規ユーザー向け文言なし（到達不能時は黙ってログのみ）。ロケールキー追加なし

## Phase 3 — `CancelledError` の区別

- `prepare.py` 外側、`session.py:play` 外側、`client.py` エラーハンドラの汎用 `except Exception` の**前**に `except asyncio.CancelledError: raise` を追加。シャットダウンを内部エラーとして誤報告・誤再試行しない
- `CancelledError` は `BaseException` 系のため現行 `except Exception` ではもともと捕捉されないが、明示することで将来の握りつぶしを防止する意図。不用意なクリーンアップawait追加はしない（キャンセル遅延防止）

## Phase 4 — 検証

- `ruff check` / `ruff format`（新規違反ゼロをベースライン差分で確認）
- オフライン単体確認：`debug_channel.send` を `RuntimeError("Session is closed")` 発火のMockに差し替え、`report_internal_error` がコード返却＋ローカルログ出力をすること、`safe_edit` / `safe_send` が False を返し例外を上げないこと、`CancelledError` が再送出されることを確認
- E2E（実切断再現）は困難のため対象外とし、コードレビューで代替

## 対象外・注意事項

- 真因の volume 400 修正（`application.yml: volume: false` → `true`＋Lavalink再起動）とは独立。本件のみ先行適用可
- 既存lintノイズには触れない。新規ヘルパーは現行スタイル（タブ・140桁・lazy `%` ログ）に合わせる
