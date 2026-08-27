# MoguTune

Discordでイントロクイズが遊べるBotです。

VCに接続し、コマンドで YouTube / Spotify / SoundCloud のプレイリストを渡すと、早押しクイズがプレイできます。

アーティストページのURLなどを使うこともできます。


## 関連リポジトリー

ロジック部分のコードは[こっち](https://github.com/Ezolys/MoguTune-Core)に分離してあります。


## 遊び方

- `/play <URL>` でクイズ開始
- `/end` で強制終了 途中で終了してもスコアなどの結果は出ます
- メッセージのコンテキストメニューからも開始できます


## 動かし方

### Dockerで動かす（推奨）

```bash
cp .env.example .env  # TOKEN とか DB_URI とか埋める
docker compose up --build -d
```

`bot` + `lavalink` の2コンテナで動きます。

### ローカルで動かす

```bash
uv sync
# or uv pip install -r requirements.txt

python main.py
```

Lavalink と MongoDB は別で用意してください。設定値は `.env.example` / `compose.yml` を参照してください。

- Python 3.13 / [uv](https://docs.astral.sh/uv/) が必要です


## 環境変数

必須なのは `TOKEN`、`DB_URI` / `DB_NAME`、`LAVALINK_*` ぐらいです。あとは任意です。

| あると動くもの | 変数 |
|---|---|
| 音量 | `MUSIC_VOLUME` / `SFX_VOLUME` |
| 効果音 | `SFX_QUIZ_*` |
| サビ再生 | `YTMRAPI_URL` / `YTMRAPI_SECRET` |
| 死活監視 | `UPTIME_KUMA_PUSH_URL` |

詳しくは `.env.example` を参照してください。


## ライセンス

[MIT License](LICENSE) — Copyright (C) 2026 Milkeyyy
