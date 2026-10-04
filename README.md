<div align="center">
<img width="1920" height="960" alt="MoguTune_Banner_GitHub" src="https://github.com/user-attachments/assets/623376e1-7643-4903-bd74-03b4e03f45ae" />
</div>

[![GitHub License](https://img.shields.io/github/license/Ezolys/MoguTune?style=for-the-badge)](./LICENSE)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/Milkeyyy?style=for-the-badge)](https://github.com/sponsors/Milkeyyy)

[![Python](https://img.shields.io/badge/python-%233670A0.svg?style=for-the-badge&logo=python&logoColor=ffdd54)](https://www.python.org)
![GitHub Release](https://img.shields.io/github/v/release/Ezolys/MoguTune?style=for-the-badge)


## 📃 概要

Discordでイントロクイズが遊べるBotです。

VCに接続し、コマンドで YouTube / Spotify / SoundCloud / Bandcamp などのプレイリストを渡すと、早押しクイズがプレイできます。

アーティストページのURLなどを使うこともできます。サーバーごとのクイズ設定やクイズ結果のリーダーボード、お気に入りプレイリストの登録にも対応しています。

> 対応しているURL/プラットフォームについては[こちら](#-対応プラットフォームについて)


## 📥 インストール

### ボットを招待

[![Invite Discord Bot](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white&label=Invite)](https://mogutune.milkeyyy.com/invite)

**ボットの稼働状況**

[![Bot Status](https://monitor.milkeyyy.com/api/badge/28/status?style=flat-square&label=Discord%20Bot)](https://status.milkeyyy.com/)

[![Lavalink Status](https://monitor.milkeyyy.com/api/badge/29/status?style=flat-square&label=Lavalink%20Node)](https://status.milkeyyy.com/)

[![Backend API Status](https://monitor.milkeyyy.com/api/badge/56/avg-response/3?style=flat-square&label=Backend%20API)](https://status.milkeyyy.com/)

> セルフホストについては[こちら](#-セルフホスト)


## 🗨️ サポートなど

### サポート Discord サーバー

ボットに関する質問などは以下の Discord サーバーからお願いします。

[![Support Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white&label=Support)](https://discord.gg/bMf9dDjndC)


### 機能要望・不具合報告

機能追加/改善要望や不具合報告は [Issue](https://github.com/Ezolys/MoguTune/issues) を作成したいただけると助かります。


## 🎮 遊び方

### クイズの開始

任意のVCに接続して `/play` コマンドを実行すると、コマンド実行者がその時参加していたVC内のメンバーを参加者としたクイズの準備が始まります。

「準備完了」ボタンを押すと参加の意思表示になり、デフォルトでは参加者の過半数が準備完了するとクイズが開始されます。

開始条件は `/settings set` から「全員」に変更することもできます。(一定時間内に条件を満たせなかった場合は中止されます)

クイズの途中でVCに参加した場合は次の問題から参加者に追加され、退出した場合は参加者から外れます。

解答ボタン等のメッセージは、コマンドを実行したテキストチャンネルに関係なく、コマンド実行者が参加しているVC内のテキストチャットに送信されます。

> URLを含むメッセージを右クリックして「アプリ」→「クイズをプレイ」を選ぶことでもクイズを開始できます。

<img width="1716" height="797" alt="image" src="https://github.com/user-attachments/assets/424b1c31-0a0d-4862-ba30-8048c1014844" />


### 解答

「解答」ボタンを押すと5つの選択肢から楽曲を選択する項目が表示され、楽曲を選択することで解答することができます。

5秒以内に解答できなかった場合は自動的に解答が終了します。

間違えた場合は **お手つき状態** となり、次の人の解答が終わるまで解答できません。

<img width="479" height="300" alt="image" src="https://github.com/user-attachments/assets/663bd280-ad10-46d3-a295-c356ae0fc0da" />

<img width="479" height="484" alt="image" src="https://github.com/user-attachments/assets/34b2f0f7-98d3-4aee-a38b-61586e6d9917" />


### クイズの終了

最後の問題が終わると自動的にクイズが終了し、トップ3のランキングと問題ごとの正解者が表示されます。表示が長い場合はページ送りボタンで前後のページに切り替えられます。

「同じ設定で再度プレイ」ボタンを押すと、同じプレイリスト、同じ出題数で再度クイズを開始することができます。

> `/end` を実行すると、クイズを強制的に終了することができます。この場合、ランキングは終了時点のスコアになります。

<img width="436" height="473" alt="image" src="https://github.com/user-attachments/assets/b00fe5f4-a57d-4c28-913d-688ef078eee5" />


### 進行方式について

デフォルトでは、次の問題への進行やスキップは参加者の投票 (過半数) で行われます。

`/settings set` で `主催者のみ` に変更すると、`/play` コマンドを実行したユーザー (**ホスト**) だけがこれらの操作を行えるようになります。
この場合、ホストがVCから退出するとクイズは終了します。


### サーバーごとに設定可能な項目

`/settings show` で現在の設定を表示、`/settings set` で変更できます。(サーバー管理権限が必要です)

| 設定項目 | 説明 | 設定値 | デフォルト |
| --- | --- | --- | --- |
| `artist_in_answers` | 解答の選択肢にアーティスト名を表示するか | `True(オン)`/`False(オフ)` | `False` |
| `progression_mode` | 次の問題への進行・スキップの方式 | `主催者のみ`/`参加者の投票 (過半数)` | `参加者の投票 (過半数)` |
| `ready_threshold` | クイズ開始に必要な準備完了の条件 | `全員`/`過半数` | `過半数` |

> YouTube のURLを使用した場合、動画のタイトルがそのまま表示されるため、`artist_in_answers` がオフの場合でもアーティスト名が含まれる場合があります。


### リーダーボード

`/leaderboard` で、サーバーごとの正解数ランキングを表示できます。

自分自身の順位や統計は `/stats` で確認できます。


## *️⃣ コマンド一覧

> `<>` で囲われたオプションは必須、`[]` で囲われたオプションは任意です。

### クイズ

- `/play <プレイリスト等のURL> [出題数 (1~50) | デフォルト: 10]`

  クイズを開始します。URLのほか、プリセット (公式プリセットとサーバーに登録したお気に入りプレイリスト) もオートコンプリートから選択できます。

  対応しているプレイリストのプラットフォームは Lavalink の設定によって異なります。詳しくは[こちら](#-対応プラットフォームについて)を参照してください。


- `/end`

  実行中のクイズを強制的に終了します。正解数などのスコアはコマンドが実行された時点の状態で終了します。


- `/sessions`

  ボットが実行しているクイズの総セッション数を表示します。


- `/leaderboard [表示件数 (1~25) | デフォルト: 10]`

  サーバーのリーダーボード (正解数ランキング) を表示します。


- `/stats`

  実行者自身のクイズ統計 (順位・累計正解数・累計参加問題数・正解率・累計参加クイズ数) を表示します。自分にのみ表示されます (ephemeral)。


- メッセージのコンテキストメニュー「クイズをプレイ」

  URLを含むメッセージから直接クイズを開始します。


### プリセット (お気に入りプレイリスト)

> すべてのコマンドにサーバー管理権限が必要です。

- `/preset add <URL> [名前] [説明]`

  お気に入りのプレイリスト (YouTube, Spotify, SoundCloud) を登録します。名前を省略するとプレイリストのタイトルが使われます。登録したプリセットは `/play` のオートコンプリートから選択できます。


- `/preset list`

  登録済みのプレイリスト一覧を表示します。


- `/preset edit <プレイリスト> [新しい名前] [新しい説明]`

  プレイリストの名前・説明を編集します。


- `/preset delete <プレイリスト>`

  プレイリストの登録を解除します。


- `/preset detail <プレイリスト>`

  プレイリストの詳細 (URL・曲数など) を表示します。


### 設定

> すべてのコマンドにサーバー管理権限が必要です。

- `/settings show`

  サーバーのクイズ設定を表示します。


- `/settings set [artist_in_answers] [progression_mode] [ready_threshold]`

  サーバーのクイズ設定を変更します。各設定項目の詳細は[サーバーごとに設定可能な項目](#サーバーごとに設定可能な項目)を参照してください。


### その他

- `/about`

  ボットのバージョンや開発者情報を表示します。


- `/ping`

  ボットの Discord Gateway の応答速度を表示します。(サーバー管理権限が必要)


- `/lavalink_node_info [node]`

  Lavalink ノードの情報を表示します。(ボットのオーナー限定)


## 🔋 セルフホスト

自分でサーバーを用意してボットを動かすこともできます。

### 必要なもの

- [Docker](https://docs.docker.com/get-docker/) / Docker Compose
- Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications) で取得)
- MongoDB ([MongoDB Atlas](https://www.mongodb.com/atlas) などのホスティングサービス、または自前のサーバー)


### Docker Compose で起動する

1. リポジトリをサブモジュール込みでクローンします。

   ```bash
   git clone --recurse-submodules https://github.com/Ezolys/MoguTune.git
   cd MoguTune
   ```

   > `core/` はサブモジュールです。クローン時に取得し忘れた場合は `git submodule update --init` を実行してください。Docker イメージのビルドに必要なため、必ず取得してからビルドしてください。

2. `.env.example` を `.env` にコピーし、必須項目を設定します。

   ```bash
   cp .env.example .env
   ```

   最低限、以下を設定すれば起動できます。その他の項目は[環境変数](#環境変数)を参照してください。

   - `TOKEN`: Discord Bot Token
   - `DB_URI`: MongoDB の接続文字列

3. コンテナを起動します。

   ```bash
   docker compose up -d --build
   ```

   Bot と Lavalink が起動します。初回は Lavalink のプラグインのダウンロードなどで起動に時間がかかることがあります。


### Lavalink を別サーバーで動かす場合

Bot と Lavalink を別々のサーバーで動かす場合は、それぞれ単体で起動できる compose ファイルを用意しています。

- `compose.bot.yml`: Bot のみを起動します (Lavalink を別サーバーで動かす場合)。`LAVALINK_HOST` の設定が必須です
- `compose.lavalink.yml`: Lavalink のみを起動します。効果音用の `./sfx` のマウントはこちら側に含まれます

```bash
# Bot サーバーで実行
docker compose -f compose.bot.yml up -d --build

# Lavalink サーバーで実行
docker compose -f compose.lavalink.yml up -d --build
```

Lavalink のポート (デフォルト: `2333`) には Bot サーバーから接続できるようにし、外部からは接続できないようにファイアウォール等で制限してください。


### ローカルで実行する (開発者向け)

Docker を使わずに直接実行することもできます。

1. Python 3.13 と [uv](https://docs.astral.sh/uv/) を用意します。

2. 依存関係をインストールします。

   ```bash
   git submodule update --init
   uv sync
   ```

3. Lavalink と MongoDB を用意します。Lavalink は `compose.lavalink.yml` を使って Lavalink のみを起動できます。

   ```bash
   docker compose -f compose.lavalink.yml up -d
   ```

   > MongoDB は別途用意し、`.env` の `DB_URI` に接続文字列を設定してください。

4. `.env` を設定して実行します。

   ```bash
   cp .env.example .env
   python main.py
   ```


### 環境変数

`.env.example` にすべての項目がコメント付きで記載されています。主な項目は以下のとおりです。

| 変数名 | 必須 | 説明 |
| --- | --- | --- |
| `TOKEN` | 必須 | Discord Bot Token |
| `DB_URI` | 必須 | MongoDB の接続文字列 |
| `DB_NAME` | 任意 | データベース名 (デフォルト: `mogutune`) |
| `LAVALINK_HOST` | 任意 | Lavalink のホスト名 (同一の compose で起動する場合は `lavalink`。別サーバー構成では必須) |
| `LAVALINK_PORT` | 任意 | Lavalink のポート (デフォルト: `2333`) |
| `LAVALINK_PASSWORD` | 任意 | Lavalink の接続パスワード (`LAVALINK_SERVER_PASSWORD` と一致させる) |
| `LAVALINK_SECURE` | 任意 | Lavalink へ `https` で接続するか (デフォルト: `false`) |
| `LAVALINK_LABEL` | 任意 | Lavalink ノードの ID (デフォルト: `LAVALINK_HOST` と同じ値) |
| `MUSIC_VOLUME` | 任意 | 楽曲の再生音量 (デフォルト: `20`) |
| `SFX_VOLUME` | 任意 | 効果音の音量 (デフォルト: `10`) |
| `MAX_SESSIONS` | 任意 | 同時に実行できるクイズの最大セッション数 (デフォルト: `0` = 無制限) |
| `SFX_QUIZ_*` | 任意 | クイズの効果音 ([効果音](#効果音)を参照) |
| `NORMALIZE_*` | 任意 | 楽曲の音量をラウドネス補正する設定 (`NORMALIZE_ENABLED` で有効/無効を切り替え) |
| `PLUGINS_LAVASRC_SPOTIFY_CLIENT_ID` / `PLUGINS_LAVASRC_SPOTIFY_CLIENT_SECRET` | 任意 | Spotify のURLを使う場合に必要 ([Spotify Developer Dashboard](https://developer.spotify.com/dashboard) で取得) |
| `SERVER_ADDRESS` / `SERVER_PORT` / `LAVALINK_SERVER_PASSWORD` | 任意 | Lavalink サーバー本体の設定 (`LAVALINK_*` 側と合わせる) |
| `UPTIME_KUMA_PUSH_URL` | 任意 | 設定すると [Uptime Kuma](https://github.com/louislam/uptime-kuma) へ死活監視の heartbeat を送信 |
| `DEBUG` / `DEBUG_GUILD_ID` / `DEBUG_LOG_GUILD_ID` / `DEBUG_LOG_TEXT_CHANNEL_ID` | 任意 | 開発・デバッグ用の設定 |


### 効果音

`./sfx` ディレクトリは Lavalink コンテナの `/opt/Lavalink/sfx` に読み取り専用でマウントされます。効果音を鳴らす場合は、このディレクトリにファイルを置き、`.env` の `SFX_QUIZ_*` に Lavalink コンテナ内の絶対パス (例: `/opt/Lavalink/sfx/correct.mp3`) または URL を設定してください。設定されていない効果音は再生されません。

| 変数名 | 再生タイミング |
| --- | --- |
| `SFX_QUIZ_Q` | 問題を出題したとき |
| `SFX_QUIZ_A` | 解答の選択肢を表示したとき |
| `SFX_QUIZ_CORRECT` | 正解したとき |
| `SFX_QUIZ_INCORRECT` | 不正解のとき |
| `SFX_QUIZ_ERROR` | 楽曲の再生に失敗したとき |


## 🎧 対応プラットフォームについて


### 直接再生することのできないプラットフォームについて

Spotify などの直接オーディオを取得することができないプラットフォームのURLを使用する場合は、楽曲のメタデータを元に YouTube などのオーディオを取得できるプラットフォームから再生されます。

そのため、一部のマイナーな楽曲などは誤ったオーディオが取得され、全く関係のない楽曲が再生されることがあります。

> これは Lavalink のプラグインである LavaSrc の仕様です。詳しくは[こちら](https://github.com/topi314/LavaSrc#what-is-mirroring)を参照してください。


### `/play` コマンドに渡すことができるURL
`/play` コマンドに渡すことができるURLは、Lavalink の設定や導入するプラグインによって異なります。

[公開インスタンス](#ボットを招待)では以下のプラットフォームに対応しています。

- YouTube / YouTube Music (プレイリスト)
  > YouTube Music のアルバムはプレイリストと同等のため対応しています
- Spotify (プレイリスト/アルバム/アーティスト)
- SoundCloud
- Bandcamp

詳しくは以下のリンク先を参照してください。

- Lavalink: https://github.com/lavalink-devs/Lavalink
- youtube-source (プラグイン): https://github.com/lavalink-devs/youtube-source
- LavaSrc (プラグイン): https://github.com/topi314/LavaSrc

> セルフホストの場合は、使用する Lavalink のプラグインや設定 (Spotify のAPIクレデンシャルなど) によって対応状況が変わります。


## 📚 関連リポジトリー

ロジック部分のコードは[こっち](https://github.com/Ezolys/MoguTune-Core)に分離してあります。


## 📜 ライセンス

[MIT License](LICENSE)

サードパーティーライセンスは [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) を参照してください。

Copyright (C) 2026 Milkeyyy
