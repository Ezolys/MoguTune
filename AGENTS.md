# AGENTS.md

## 開発コマンド

```bash
# 依存インストール
uv pip install -r requirements.txt

# リント (ruff select = ["ALL"], pyproject.toml で設定済み)
ruff check mogutune/ main.py

# フォーマット (タブインデント, 行長140)
ruff format mogutune/ main.py

# ローカル実行
python main.py

# ロケール差分チェック (core リポジトリのテストで実施)
# V:\MoguTune-Core で: uv run pytest tests/test_locales.py
```

テストフレームワーク・型チェックは未導入 (core リポジトリには pytest あり)。

## Python / 環境

- **Python 3.13 必須** (`.python-version` / `requires-python = ">=3.13"`)
- パッケージ管理は **uv**。`requirements.txt` は `uv export` で自動生成（手編集禁止）。`[tool.uv] exclude-newer = "1 week"` で1週間以内のリリースのみ解決
- `main.py` は dotenv のロードを試みて失敗しても続行する（本番では compose で環境変数を注入）
- **モジュール import 時の副作用**:
  - `mogutune/app.py` はモジュール読み込み時に `App.load_pyproject()` を実行する。**`pyproject.toml` が存在しないと失敗する**
  - `mogutune/client.py` の import で `setup_logging()` (`mogutune/logger.py`) が実行され、`./logs/` ディレクトリが作成される
- ローカル実行には Lavalink サーバーと MongoDB が別途必要（`.env.example` / `compose.yml` 参照）

## アーキテクチャ要点

- **エントリポイント**: `main.py` → `mogutune/client.py:run()` で locale 読込 → Cog 読込 → コマンドのローカライズ → Bot 起動
- **Cog のロード**: `client.load_extensions("mogutune.cogs.commands")` — Cog モジュールは `mogutune/cogs/commands/` 直下に `.py` ファイルとして置く（`dev.py` / `general.py` / `quiz.py`。`cogs/commands/` には `__init__.py` 不要）
- **DB**: `mogutune_core.db.DBManager` (`mogutune-core` パッケージ) を `on_ready` で `connect()`（`DB_URI` / `DB_NAME` 環境変数必須、失敗時は `ConnectionError` 送出 → bot 側で `sys.exit(1)`）。全操作は `pymongo.AsyncMongoClient` 経由。コレクションは `presets` / `guild_settings` / `playlists` (`playlists` は `/playlist` コマンドで管理するサーバーごとのプレイリスト)
- **Lavalink**: sonolink を使用。ノード情報は環境変数 `LAVALINK_HOST` / `LAVALINK_PORT` / `LAVALINK_PASSWORD` / `LAVALINK_SECURE` / `LAVALINK_LABEL`（ノード ID として使用）から読み込み。`LAVALINK_SECURE=true` の場合は `https://` URI 形式で登録する（sonolink 1.3.0 の `create_node` に secure 引数がないため）。ノード登録は Bot の `__init__` で同期的に行い、接続（`sl_client.start()`）は py-cord の `on_connect` で最大5回・5秒間隔でリトライし、全失敗時は `sys.exit(1)` と KumaSan error ping。自動切断 (Inactivity) は無効化し、切断管理はクイズセッション側に一任する
- **ボイス接続**: `voice_channel.connect(cls=sonolink.Player)` (`quiz/prepare.py`) — sonolink の Player クラスを使う。検索は `sl_client.search_track()` で行い、`SearchResult` を `track_adapter.unpack_search()` で正規化する（エラー・空結果は None）
- **クイズ**: `mogutune/quiz/` サブパッケージ（manager / session / views / prepare / events / track_adapter に分割、`__init__.py` で全公開。`player.py` は core の再エクスポート）。`quiz_session_manager` シングルトンが guild_id をキーに管理し、1ギルドにつき1セッションまで。**ゲームロジック (Roster / trackpool / answers / ranking) は `mogutune-core` パッケージの純粋ロジックを使用**。`session.py` はオーケストレーション (Discord UI / sonolink 再生 / SFX / ロケール写像) のみを担い、`track_adapter.py` が sonolink.Playable ↔ core.Track の変換を集約する (変換はこの1箇所のみ)
- **プリセット更新**: `on_ready` で1時間おきに `update_presets` タスクが起動し、Cog `QuizCommands.load_presets()` が DB からプリセットを再読込する
- **効果音 (SFX)**: `mogutune/sfx.py` の `SFX` Enum が `SFX_QUIZ_{CORRECT,INCORRECT,Q,A,ERROR}` 環境変数からパスを読み込み。未設定の SFX はスキップされる
- **サビ検出**: `mogutune/chorus.py` の `YTMostReplayedAPI` が `YTMRAPI_URL` / `YTMRAPI_SECRET` の外部 API からサビ再生位置 (ミリ秒) を取得
- **死活監視**: `mogutune/kumasan.py` の `KumaSan` が Uptime Kuma へ heartbeat を送信。`UPTIME_KUMA_PUSH_URL` 未設定ならスキップ。`on_ready` 時と1分ごとの `send_heartbeat` ループ、Lavalink 接続失敗時にも ping 送信
- **共通モジュール**:
  - `app.py`: `App` クラス — pyproject.toml から名前・バージョンを読み込み、開発者情報を保持（`/about` で使用）
  - `embeds.py`: `EmbedsTemplates` — info/success/warning/error/internal_error の埋め込みテンプレート。応答メッセージはこれを使う
  - `debug_logger.py`: `DebugLogger.report_internal_error()` — 内部例外をデバッグチャンネルへ投稿し UUID7 ベースのエラーコードを返す
  - `logger.py`: `setup_logging()` — コンソール INFO + `logs/app.log` へローテーション出力 (5MB×5)
  - `localizations.py`: `Localization` — pycord-localizer の `I18n` ラッパー + 手動翻訳用 `translate()`
  - `url_query_labels.py`: `/play` の URL オートコンプリート用に Spotify / YouTube / SoundCloud の URL 種別判定とローカライズ済みラベル生成

## 多言語

- ロケールファイル: **`mogutune-core` パッケージ内** (`mogutune_core/locales/{ja,en_GB}.json`、`importlib.resources` で読み込み)。単一ソース化のため bot リポジトリには置かない
- `pycord-localizer` (`consider_user_locale=True`) でユーザー設定を反映
- 存在しないロケールのリクエストは `en_GB` にフォールバック
- ja/en_GB 間のキー差分は core リポジトリの `tests/test_locales.py` (pytest) で検出する。キーのリネームは禁止 (追加のみ許可)

## デバッグモード

環境変数 `DEBUG=true` で以下が有効化:
- `client.debug_guilds` にハードコードされたギルドID (`client.py:72`) が設定され、コマンド同期が高速化。テスト用ギルドを追加する場合はこのリストを編集する。

`DEBUG_GUILD_ID` / `DEBUG_TEXT_CHANNEL_ID` が設定されていれば `on_ready` で `DebugLogger` が初期化され、内部エラー発生時に UUID7 ベースのエラーコードとトレースバックを Debug チャンネルに投稿する（DEBUG 変数とは独立）。

## デプロイ

`compose.yml` で `bot` + `lavalink` の2サービス（Bot 側は `./` を `/code/logs` にマウント）。Bot イメージは `Dockerfile` で COPY 命令は指定ファイルのみ（全ファイルをコピーしない）。Lavalink は `Dockerfile.lavalink` + `application.yml` の設定を使い、`lavasrc-plugin` と `youtube-plugin` が必須。環境変数はすべて `.env.example` に定義。

## コードスタイル

- **インデント**: タブ（スペース禁止）
- **行長**: 140文字
- **ruff**: `select = ["ALL"]`、`pyproject.toml` で多くのルールを ignore（D1系 docstring ルール, COM812 末尾カンマ, BLE001, ERA001, SIM105 等）
- **リント unfixable**: F401（未使用 import）, F841（未使用変数）は自動修正しない
- McCabe 複雑度: 最大30 / pylint max-branches: 最大30
- pylint max-args: 最大6
