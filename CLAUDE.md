# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

MoguTune - Discord イントロクイズボット。py-cord (Discord.py fork) + Lavalink で音声再生、MongoDB でデータ管理、日本語/英語の多言語対応。

## コマンド

```bash
# 実行
python main.py

# リント
ruff check mogutune/ main.py

# フォーマット
ruff format mogutune/ main.py

# 依存パッケージインストール
uv pip install -r requirements.txt
```

テストフレームワークは未導入。

## コードスタイル

- **インデント**: タブ
- **行長**: 140文字
- **リンター/フォーマッター**: ruff (pyproject.toml で設定済み)

## アーキテクチャ

- **エントリポイント**: `main.py` → `mogutune/client.py:run()`
- **Bot初期化**: Discord.Bot作成 → Lavalinkノード接続 → ロケール読込 → Cogロード → コマンドローカライズ → Bot実行
- **Cog構成** (`mogutune/cogs/commands/`):
  - `quiz.py` - クイズコマンド (`/play`, `/end`)
  - `general.py` - 一般コマンド (`/ping`, `/about`, `/sessions`)
  - `dev.py` - 開発者専用コマンド (`/lavalink_node_info`, `/get_youtube_video_info`)
- **クイズセッション** (`quiz_session.py`): `QuizSessionManager` がセッション状態・ライフサイクルを管理。Discord View パターンでボタン/モーダル UI を実装
- **DB** (`db.py`): MongoDB (pymongo) でプリセット等を管理
- **音声**: mafic (Lavalink クライアント) で再生。`chorus.py` が YTMostReplayedAPI と連携しサビ区間を取得
- **効果音** (`sfx.py`): Enum ベースで効果音パスを管理。`resources/sfx/` に正解/不正解/出題/解答の MP3 を格納
- **多言語**: `pycord-localizer` + `mogutune/resources/locales/{ja,en_GB}.json`。`check_diff.py` でロケールファイルのキー差分を検出
- **アプリ情報** (`app.py`): バージョン・開発者情報等を一元管理
- **Embed テンプレート** (`embeds.py`): info/success/warning/error の埋め込みメッセージテンプレート
- **エラーレポート** (`debug_logger.py`): UUID7ベースのエラーコード生成、デバッグチャンネルへ詳細投稿
- **ロギング** (`logger.py`): Console (INFO+) + RotatingFile (`./logs/app.log`, 5MB×5世代)
- **死活監視** (`kumasan.py`): Uptime Kuma へ定期的にプッシュ通知を送信

## デプロイ

Docker Compose (`compose.yml`) で `bot` + `lavalink` の2サービス構成。
- `Dockerfile` - Python 3.13-slim-bookworm ベースの Bot コンテナ
- `Dockerfile.lavalink` - Lavalink v4.2.2 コンテナ (`application.yml` + SFX ファイルを同梱)

## 環境変数

`.env.example` 参照。主要なもの: `TOKEN` (Discord), `DB_URI`/`DB_NAME` (MongoDB), `LAVALINK_*` (音声サーバー), `YTMRAPI_*` (サビ取得API), `UPTIME_KUMA_PUSH_URL` (死活監視)
