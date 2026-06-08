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

# ロケール差分チェック
python mogutune/check_diff.py
```

テストフレームワーク・型チェックは未導入。

## Python / 環境

- **Python 3.13 必須** (`.python-version` / `requires-python = ">=3.13"`)
- パッケージ管理は **uv**。`requirements.txt` は `uv export` で自動生成（手編集禁止）
- `main.py` は dotenv のロードを試みて失敗しても続行する（本番では compose で環境変数を注入）
- `mogutune/` 以下のパッケージには `__init__.py` が一部ない（ruff INP001 無視で対応）

## アーキテクチャ要点

- **エントリポイント**: `main.py` → `mogutune/client.py:run()` で locale 読込 → Cog 読込 → ローカライズ → Bot 起動
- **Cog のロード**: `client.load_extensions("mogutune.cogs.commands")` — Cog モジュールは `mogutune/cogs/commands/` 直下に置く
- **DB**: `DBManager` は `on_ready` で非同期接続。全操作は `pymongo.AsyncMongoClient` 経由。コレクション名は `presets` 固定
- **Lavalink**: mafic を使用。ノード追加は Bot の `__init__` で `self.loop.create_task()` 経由、最大5回・5秒間隔でリトライし、全失敗時は `sys.exit(1)`
- **ボイス接続**: `voice_channel.connect(cls=mafic.Player)` — mafic の Player クラスを使う
- **クイズセッション**: `QuizSessionManager` が guild_id をキーに管理。1ギルドにつき1セッションまで
- **効果音 (SFX)**: 環境変数で URL またはローカルファイルの絶対パスを指定。未設定の SFX はスキップされる

## 多言語

- ロケールファイル: `mogutune/resources/locales/{ja,en_GB}.json`
- `pycord-localizer` + `consider_user_locale=True` でユーザー設定を反映
- 存在しないロケールのリクエストは `en_GB` にフォールバック
- `check_diff.py` で ja/en_GB 間のキー差分を検出可能

## デバッグモード

環境変数 `DEBUG=true` で以下が有効化:
- `client.debug_guilds` に特定ギルドIDが設定され、コマンド同期が高速化
- `DEBUG_GUILD_ID` / `DEBUG_TEXT_CHANNEL_ID` が設定されていれば、内部エラー発生時に UUID7 ベースのエラーコードとトレースバックを Debug チャンネルに投稿

## デプロイ

`compose.yml` で `bot` + `lavalink` の2サービス。Bot コンテナの COPY 命令は指定ファイルのみ（全ファイルをコピーしない）。Lavalink は `application.yml` の設定を使い、`lavasrc-plugin` と `youtube-plugin` が必須。

## コードスタイル

- **インデント**: タブ（スペース禁止）
- **行長**: 140文字
- **ruff**: `select = ["ALL"]`、`pyproject.toml` で多くのルールを ignore（D1系 docstring ルール, COM812 末尾カンマ等）
- **リント unfixable**: F401（未使用 import）, F841（未使用変数）は自動修正しない
- McCabe 複雑度: 最大30
- pylint max-args: 最大6
