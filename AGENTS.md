# AGENTS.md

## 開発コマンド

```bash
# サブモジュール初期化 (clone 直後 / Core 更新後)
git submodule update --init

# 依存インストール
uv sync

# リント (ruff select = ["ALL"], pyproject.toml で設定済み)
ruff check mogutune/ main.py

# フォーマット (タブインデント, 行長140)
ruff format mogutune/ main.py

# ローカル実行
python main.py

# ロケール差分チェック (core サブモジュールのテストで実施)
# core ディレクトリで: uv run pytest tests/test_locales.py

# ダッシュボード サーバー (dashboard/server)
# ruff check . / ruff format . / uv run pytest

# ダッシュボード クライアント (dashboard/client)
# npm install / npm run dev / npm run build (tsc --noEmit + vite build)
```

テストフレームワーク・型チェックは未導入 (core サブモジュールと dashboard/server には pytest あり)。

## Python / 環境

- **Python 3.13 必須** (`.python-version` / `requires-python = ">=3.13"`)
- パッケージ管理は **uv**。`mogutune-core` は `core/` サブモジュール (`MoguTune-Core`) を `[tool.uv.sources]` の editable path 参照で取り込み、サブモジュールのコミットで固定する。`requirements.txt` は `uv export -o requirements.txt --no-hashes --no-dev` で自動生成（手編集禁止）。`[tool.uv] exclude-newer = "1 week"` で1週間以内のリリースのみ解決
- `main.py` は dotenv のロードを試みて失敗しても続行する（本番では compose で環境変数を注入）
- **モジュール import 時の副作用**:
  - `mogutune/app.py` はモジュール読み込み時に `App.load_pyproject()` を実行する。**`pyproject.toml` が存在しないと失敗する**
  - `mogutune/client.py` の import で `setup_logging()` (`mogutune/logger.py`) が実行され、`./logs/` ディレクトリが作成される
- ローカル実行には Lavalink サーバーと MongoDB が別途必要（`.env.example` / `compose.yml` 参照）

## アーキテクチャ要点

- **リポジトリ構成**: `core/` は [MoguTune-Core](https://github.com/Ezolys/MoguTune-Core) の git submodule（クイズの純粋ロジック `mogutune_core` とロケールの単一ソース）。clone 時は `--recurse-submodules` が必要で、Core 更新は `cd core && git pull` → 親リポジトリで `git add core` してコミットする
- **エントリポイント**: `main.py` → `mogutune/client.py:run()` で locale 読込 → Cog 読込 → コマンドのローカライズ → Bot 起動
- **Cog のロード**: `client.load_extensions("mogutune.cogs.commands")` — Cog モジュールは `mogutune/cogs/commands/` 直下に `.py` ファイルとして置く（`dev.py` / `general.py` / `quiz.py`。`cogs/commands/` には `__init__.py` 不要）
- **DB**: `mogutune_core.db.DBManager` (`mogutune-core` パッケージ) を `on_ready` で `connect()`（`DB_URI` / `DB_NAME` 環境変数必須、失敗時は `ConnectionError` 送出 → bot 側で `sys.exit(1)`）。全操作は `pymongo.AsyncMongoClient` 経由。コレクションは `presets` / `guild_settings` / `playlists` / `leaderboard` (`playlists` は `/playlist` コマンド、`leaderboard` は `/leaderboard` コマンドで扱う) に加え、ダッシュボード向けの `command_logs` / `internal_errors` / `bot_status` / `guilds` / `quiz_history` / `bot_state`
- **Lavalink**: sonolink を使用。ノード情報は環境変数 `LAVALINK_HOST` / `LAVALINK_PORT` / `LAVALINK_PASSWORD` / `LAVALINK_SECURE` / `LAVALINK_LABEL`（ノード ID として使用）から読み込み。`LAVALINK_SECURE=true` の場合は `https://` URI 形式で登録する（sonolink 1.3.0 の `create_node` に secure 引数がないため）。ノード登録は Bot の `__init__` で同期的に行い、接続（`sl_client.start()`）は py-cord の `on_connect` で最大5回・5秒間隔でリトライし、全失敗時は `sys.exit(1)` と KumaSan error ping。接続後は `on_ready` から5分間隔の監視タスク (`check_lavalink_nodes`) が動き、未接続ノードは `node.reconnect()` で再接続する（sonolink の自動再接続が retries を使い切った後は `connect()` が無視されるため）。接続済みでも REST (`/v4/info`) が10秒応答しなければゾンビ接続とみなして `node.reconnect()` する。自動切断 (Inactivity) は無効化し、切断管理はクイズセッション側に一任する
- **ボイス接続**: `voice_channel.connect(cls=sonolink.Player)` (`quiz/prepare.py`) — sonolink の Player クラスを使う。検索は `sl_client.search_track()` で行い、`SearchResult` を `track_adapter.unpack_search()` で正規化する（エラー・空結果は None）
- **クイズ**: `mogutune/quiz/` サブパッケージ（manager / session / views / prepare / events / results に分割、`__init__.py` で全公開。`player.py` は core の再エクスポート）。`quiz_session_manager` シングルトンが guild_id をキーに管理し、1ギルドにつき1セッションまで。**ゲームロジック (Roster / trackpool / answers / ranking) は `mogutune-core` パッケージの純粋ロジックを使用**。`session.py` はオーケストレーション (Discord UI / sonolink 再生 / SFX / ロケール写像) のみを担い、`mogutune/track_adapter.py` (quiz パッケージ外) が sonolink.Playable ↔ core.Track の変換を集約する (変換はこの1箇所のみ)。`resolve_youtube_url()` も同ファイルにあり、サビ検出 (`QuizSession.resolve_youtube_track_uri` はデリゲート) と normalizer の LUFS 解析 URL 解決で共用する。終了画面はトップ3ランキング + 問題ごとの正解者を表示し、文字数上限を超える場合は `results.py` の `truncate_lines` / `paginate_lines` で省略・ページ分割する (`QuizEndView` のページ送りボタン)。問題ごとの正解者 ID は `QuizSession.q_results`、プレイヤーごとの参加問題数は `QuizSession.participant_questions` に記録する
- **リーダーボード**: `mogutune/leaderboard.py` が `leaderboard` コレクション (`_id = "{guild_id}:{user_id}"`) へクイズ終了時に正解数・参加問題数 (プレイヤーごとの在籍問題数)・参加クイズ数を加算し、`/leaderboard` コマンド (`general.py`) がギルド単位の上位 N 件と実行者自身の順位を表示する
- **プリセット更新**: `on_ready` で1時間おきに `update_presets` タスクが起動し、Cog `QuizCommands.load_presets()` が DB からプリセットを再読込する
- **効果音 (SFX)**: `mogutune/sfx.py` の `SFX` Enum が `SFX_QUIZ_{CORRECT,INCORRECT,Q,A,ERROR}` 環境変数からパスを読み込み。URL または Lavalink内の絶対パス（`/opt/Lavalink/sfx/` 配下のみ許可、`session.py::resolve_sfx_track` で検査。Lavalink v4 の local ソースは生の絶対パスを identifier に要求するため、`source=None` を明示して `search_track` に素通しする）を指定し、未設定・解決不可の SFX はスキップされる
- **サビ検出**: `mogutune/chorus.py` の `YTMostReplayedAPI` が `BACKEND_API_URL` / `BACKEND_API_SECRET` の外部 API からサビ再生位置 (ミリ秒) を取得
- **ラウドネス**: `mogutune/normalizer.py` が `BACKEND_API_URL` (YTMRAPI の `/lufs`) から LUFS を取得し再生音量を補正。LavaDSPX ピークリミッターも同モジュールで適用。クイズ開始時は準備完了後に全曲の解析完了を待つ (`NORMALIZE_PREFETCH_TIMEOUT_S`、進捗表示は同モジュールの `PROGRESS` 定数で無効化)。解析タスクは in-flight 共有され、2 秒タイムアウト後もバックグラウンドで継続し完了時に LRU → Mongo `loudness_cache` に保存。Spotify 起源曲は `track_adapter.resolve_youtube_url()` で解決した YouTube URL を解析に使用
- **死活監視**: `mogutune/kumasan.py` の `KumaSan` が Uptime Kuma へ heartbeat を送信。`UPTIME_KUMA_PUSH_URL` 未設定ならスキップ。`on_ready` 時と1分ごとの `send_heartbeat` ループ、Lavalink 接続失敗時にも ping 送信
- **共通モジュール**:
  - `app.py`: `App` クラス — pyproject.toml から名前・バージョンを読み込み、開発者情報を保持（`/about` で使用）
  - `embeds.py`: `EmbedsTemplates` — info/success/warning/error/internal_error の埋め込みテンプレート。応答メッセージはこれを使う
  - `debug_logger.py`: `DebugLogger.report_internal_error()` — 内部例外を UUID7 ベースのエラーコード付きでデバッグチャンネルへ投稿し、同時に `internal_errors` へ記録する（`source` / `guild_id` / `user_id` / `command` を任意で受け取る）
  - `logger.py`: `setup_logging()` — コンソール INFO + `logs/app.log` へローテーション出力 (5MB×5)
  - `localizations.py`: `Localization` — pycord-localizer の `I18n` ラッパー + 手動翻訳用 `translate()`
  - `url_query_labels.py`: `/play` の URL オートコンプリート用に Spotify / YouTube / SoundCloud の URL 種別判定とローカライズ済みラベル生成
- **テレメトリ (ダッシュボード向け)**: `mogutune/telemetry.py` が `command_logs` / `internal_errors` / `bot_status` / `guilds` / `quiz_history` への記録を集約する。すべて失敗しても本処理を止めない。`on_ready` で `ensure_indexes()`（TTL: command_logs 90日, internal_errors 180日）と `sync_guilds()` を実行し、30秒間隔の `report_bot_status` タスクが `QuizSession.status_snapshot()` と Lavalink ノード状態を `bot_status` へ書き込む。コマンドの成否は `client.py` の `on_application_command_completion` / `on_application_command_error` から記録し、`on_guild_join` / `on_guild_remove` で `guilds` を同期する。クイズ終了時は `session.py` が `quiz_history` を記録する
- **メンテナンスモード**: `mogutune/maintenance.py` が `bot_state` (`_id = "maintenance"`) を読み書きする。`prepare_play` の冒頭で `fetch_state()` を確認し、有効なら `cmd.start.maintenance_mode` (またはダッシュボードで設定した任意メッセージ) を返して開始しない。ダッシュボードの `PUT /api/maintenance` と Bot の `/maintenance` コマンド (オーナー専用, `dev.py`) の両方から切り替えられる
- **管理ダッシュボード**: `dashboard/` (モノレポ内、Bot とは独立したコンテナ)。`server/` は FastAPI + uv (MongoDB を読み、メンテナンスのみ書き込む)。`client/` は React 19 + Vite + TS + Tailwind v4 + DaisyUI 5 + lucide-react + TanStack Query + Recharts。デザインは「スタジオ計器盤」テーマ (ダーク固定のカスタム DaisyUI テーマ + DotGothic16 / Zen Kaku Gothic New / IBM Plex Mono)。認証は Cloudflare Access (Zero Trust) に一任し、オリジン側で `Cf-Access-Jwt-Assertion` を JWKS 検証 (`access.py`) するほか、更新系リクエストは Origin チェックで CSRF 対策する。`DASHBOARD_AUTH_DISABLED=true` は開発時のみ。集計は MongoDB の aggregation で行い、日付の区切りは `DASHBOARD_TIMEZONE` (デフォルト Asia/Tokyo)。API は `/api/status` `/api/guilds` `/api/commands/*` `/api/quiz/*` `/api/errors/*` `/api/maintenance`

## 多言語

- ロケールファイル: **`mogutune-core` パッケージ内** (`mogutune_core/locales/{ja,en_GB}.json`、`importlib.resources` で読み込み)。単一ソース化のため bot リポジトリには置かない
- `pycord-localizer` (`consider_user_locale=True`) でユーザー設定を反映
- 存在しないロケールのリクエストは `en_GB` にフォールバック
- ja/en_GB 間のキー差分は core サブモジュールの `tests/test_locales.py` (pytest) で検出する。キーのリネームは禁止 (追加のみ許可)
- メンテナンス関連のキー (`cmd.start.maintenance_mode` / `cmd.maintenance.*` と `commands.maintenance`) は core 側に追加済み

## デバッグモード

環境変数 `DEBUG=true` で以下が有効化:
- `client.debug_guilds` にハードコードされたギルドID (`client.py:72`) が設定され、コマンド同期が高速化。テスト用ギルドを追加する場合はこのリストを編集する。

`DEBUG_GUILD_ID` / `DEBUG_TEXT_CHANNEL_ID` が設定されていれば `on_ready` で `DebugLogger` が初期化され、内部エラー発生時に UUID7 ベースのエラーコードとトレースバックを Debug チャンネルに投稿する（DEBUG 変数とは独立）。

## デプロイ

`compose.yml` で `bot` + `lavalink` の2サービス（Bot 側は `./` を `/code/logs` にマウント、Lavalink 側は `./sfx` を `/opt/Lavalink/sfx` に `:ro` でマウント）。Bot イメージは `Dockerfile` で COPY 命令は指定ファイルのみ（全ファイルをコピーしない）。`core/` サブモジュールは editable インストールのため `/code/core` へコピーするので、**ビルド前に `git submodule update --init` が必須**。ビルドコンテキストは `.dockerignore` で `.venv` / `__pycache__` / `.git` などを除外する。Lavalink は `Dockerfile.lavalink` + `application.yml` の設定を使い、`lavasrc-plugin` と `youtube-plugin` が必須。環境変数はすべて `.env.example` に定義。Bot と Lavalink を別サーバーで動かす場合は `compose.bot.yml`（Bot のみ。`LAVALINK_HOST` は `${LAVALINK_HOST:?error}` で必須）と `compose.lavalink.yml`（Lavalink のみ。`./sfx` マウントはこちら側）を使い、それぞれ `docker compose -f compose.bot.yml up -d --build` / `docker compose -f compose.lavalink.yml up -d --build` で起動する。`lavalink-plugins` ボリュームは各 compose ファイルで top-level `volumes` に宣言する（未宣言だと Compose v5 以降で `invalid compose project` になる）。ダッシュボードは `compose.dashboard.yml`（`dashboard/Dockerfile` のマルチステージで client を build → FastAPI が `/app/static` を配信）で起動し、`127.0.0.1:${DASHBOARD_PORT:-8787}` にのみ公開する。cloudflared は同じホストで `http://localhost:8787` へルーティングし、Cloudflare Access の JWT をオリジン側でも検証する。

## コードスタイル

- **インデント**: タブ（スペース禁止）
- **行長**: 140文字
- **ruff**: `select = ["ALL"]`、`pyproject.toml` で多くのルールを ignore（D1系 docstring ルール, COM812 末尾カンマ, BLE001, ERA001, SIM105 等）
- **リント unfixable**: F401（未使用 import）, F841（未使用変数）は自動修正しない
- McCabe 複雑度: 最大30 / pylint max-branches: 最大30
- pylint max-args: 最大6
