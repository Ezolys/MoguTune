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
  - `quiz.py` - クイズコマンド
  - `general.py` - 一般コマンド (ping等)
  - `dev.py` - 開発者専用コマンド (オーナーのみ)
- **クイズセッション** (`quiz_session.py`): `QuizSessionManager` がセッション状態・ライフサイクルを管理。Discord View パターンでボタン/モーダル UI を実装
- **DB** (`db.py`): MongoDB (pymongo) でプリセット等を管理
- **音声**: mafic (Lavalink クライアント) で再生。`chorus.py` が YTMostReplayedAPI と連携しサビ区間を取得
- **多言語**: `pycord-localizer` + `mogutune/resources/locales/{ja,en_GB}.json`
- **エラーレポート** (`debug_logger.py`): UUID7ベースのエラーコード生成、デバッグチャンネルへ詳細投稿
- **ロギング** (`logger.py`): Console (INFO+) + RotatingFile (`./logs/app.log`, 5MB×5世代)

## 環境変数

`.env.example` 参照。主要なもの: `TOKEN` (Discord), `DB_URI`/`DB_NAME` (MongoDB), `LAVALINK_*` (音声サーバー)
