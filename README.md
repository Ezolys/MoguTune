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

アーティストページのURLなどを使うこともできます。サーバーごとのクイズ設定やクイズ結果のリーダーボード、よく使うプレイリストの保存にも対応しています。

> 対応しているURL/プラットフォームについては[こちら](#-対応プラットフォームについて)


## 📥 インストール

### ボットを招待

[![Invite Discord Bot](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white&label=Invite)](https://discord.com/oauth2/authorize?client_id=1419676092314161193)

**ボットの稼働状況**

[![Bot Status](https://monitor.milkeyyy.com/api/badge/28/status?style=flat-square&label=Discord%20Bot)](https://status.milkeyyy.com/)

[![Lavalink Status](https://monitor.milkeyyy.com/api/badge/29/status?style=flat-square&label=Lavalink%20Node)](https://status.milkeyyy.com/)

> セルフホストについては[こちら](#-セルフホスト)


## 🗨️ サポートなど

### サポート Discord サーバー

ボットに関する質問や不具合報告等は以下の Discord サーバーからお願いします。

[![Support Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white&label=Support)](https://discord.gg/bMf9dDjndC)


### 機能要望・不具合報告

機能追加/改善要望や不具合報告は [Issue](https://github.com/Ezolys/MoguTune/issues) を作成したいただけると助かります。


## 🎮 遊び方

### クイズの開始

任意のVCに接続して `/play` コマンドを実行すると、コマンド実行者がその時参加していたVC内のメンバーを参加者としたクイズの準備が始まります。

「準備完了」ボタンを押すと参加の意思表示になり、デフォルトでは参加者の過半数が準備完了するとクイズが開始されます。開始条件は `/settings` で「全員」に変更することもできます。(一定時間内に条件を満たせなかった場合は中止されます)

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

デフォルトでは、次の問題への進行やスキップは参加者の投票 (過半数) で行われます。`/settings` で「主催者のみ」に変更すると、`/play` コマンドを実行した **ホスト** だけがこれらの操作を行えるようになります。

ホストがVCから退出すると、クイズは終了します。


### サーバーごとの設定

`/settings show` で現在の設定を表示、`/settings set` で変更できます。(サーバー管理権限が必要です)

| 設定項目 | 説明 | デフォルト |
| --- | --- | --- |
| 解答候補にアーティスト名を含める | 解答の選択肢にアーティスト名を表示するか | オフ |
| 進行方式 | 次の問題への進行・スキップの方式 | 参加者の投票 (過半数) |
| クイズ開始の準備完了条件 | クイズ開始に必要な準備完了の条件 | 過半数 |


### 解答の選択肢について

使用するプレイリストのプラットフォームによって、選択肢に表示される楽曲名の表記が異なります。

YouTube のURLを使用した場合、動画のタイトルがそのまま表示されるため、アーティスト名も含まれる場合があります。

ボーカルなどからアーティストを予想し、アーティスト名だけで解答できるのを防ぎたい場合は、YouTube Music や Spotify のURLを使用してください。

> YouTube Music のURLを使用しても、楽曲によってはMVなどのタイトルが表示される場合があります。

なお、`/settings` の「解答候補にアーティスト名を含める」をオンにすると、選択肢にアーティスト名が追加表示されます。


### リーダーボード

`/leaderboard` で、サーバーごとの正解数ランキングを表示できます。

正解率や実行者自身の順位もあわせて表示されます。


## *️⃣ コマンド一覧

> `<>` で囲われたオプションは必須、`[]` で囲われたオプションは任意です。

### クイズ

- `/play <プレイリスト等のURL> [出題数 (1~50) | デフォルト: 10]`

  クイズを開始します。URLのほか、プリセットやサーバーに保存したプレイリストもオートコンプリートから選択できます。

  対応しているプレイリストのプラットフォームは Lavalink の設定によって異なります。詳しくは[こちら](#-対応プラットフォームについて)を参照してください。


- `/end`

  実行中のクイズを強制的に終了します。正解数などのスコアはコマンドが実行された時点の状態で終了します。


- `/sessions`

  ボットが実行しているクイズの総セッション数を表示します。


- `/leaderboard [表示件数 (1~25) | デフォルト: 10]`

  サーバーのリーダーボード (正解数ランキング) を表示します。実行者自身の順位と正解率もあわせて表示されます。


- メッセージのコンテキストメニュー「クイズをプレイ」

  URLを含むメッセージから直接クイズを開始します。


### プレイリスト

> すべてのコマンドにサーバー管理権限が必要です。

- `/playlist new <名前> <説明> [プレイリストのURL] [楽曲のURL...]`

  プレイリストを新規作成します。既存のプレイリストのURLを渡すと、その内容を取り込むことができます。


- `/playlist add <プレイリスト> <楽曲のURL...>`

  プレイリストに楽曲を追加します。楽曲のURLは半角スペース区切りで複数指定できます。


- `/playlist edit <プレイリスト> [新しい名前] [新しい説明]`

  プレイリストの名前・説明を編集します。


- `/playlist delete <プレイリスト>`

  プレイリストを削除します。


- `/playlist detail <プレイリスト>`

  プレイリストの詳細 (登録されている楽曲など) を表示します。


### 設定

> すべてのコマンドにサーバー管理権限が必要です。

- `/settings show`

  サーバーのクイズ設定を表示します。


- `/settings set [artist_in_answers] [progression_mode] [ready_threshold]`

  サーバーのクイズ設定を変更します。各設定項目の詳細は[サーバーごとの設定](#サーバーごとの設定)を参照してください。


### その他

- `/about`

  ボットのバージョンや開発者情報を表示します。


- `/ping`

  ボットの応答速度を表示します。(サーバー管理権限)


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


### 管理ダッシュボード

Bot の稼働状況・コマンド実行ログ・クイズの実行状況・内部エラーを Web から閲覧でき、メンテナンスモードを切り替えられるダッシュボードです (`dashboard/`)。Bot とは独立したコンテナとして動作し、MongoDB を介してデータを共有します。

認証は Cloudflare Access (Zero Trust) に任せ、オリジン側でも `Cf-Access-Jwt-Assertion` ヘッダを検証するため、Access を迂回した直接アクセスは拒否されます。

#### セットアップ

1. Cloudflare Zero Trust で Access アプリケーションを作成し、許可するメールアドレスなどのポリシーを設定します。アプリケーションの **AUD タグ (Application Audience)** を控えます。
2. 既存トンネル (cloudflared) の ingress にダッシュボードのホスト名を追加します。

   ```yaml
   ingress:
     - hostname: mogutune-dashboard.example.com
       service: http://localhost:8787
   ```

3. `.env` に `CF_ACCESS_TEAM_DOMAIN` (例: `https://myteam.cloudflareaccess.com`) と `CF_ACCESS_AUD` を設定します。
4. 起動します。

   ```bash
   docker compose -f compose.dashboard.yml up -d --build
   ```

ダッシュボードは `127.0.0.1:8787` にのみ公開されるため、cloudflared と同じホストで動かしてください。別サーバーで動かす場合は `compose.dashboard.yml` の `ports` とトンネルの ingress を環境に合わせて変更します (DB_URI は Bot と同じ接続先を指定)。

> `DASHBOARD_AUTH_DISABLED=true` は認証を完全にスキップする開発用の設定です。本番では絶対に有効にしないでください。

#### ローカルで開発する

```bash
# サーバー (認証を無効化して起動)
cd dashboard/server
DB_URI="mongodb://..." DASHBOARD_AUTH_DISABLED=true uv run uvicorn mogutune_dashboard.main:app --port 8787

# クライアント (http://localhost:5173 で起動し、/api をサーバーへプロキシ)
cd dashboard/client
npm install
npm run dev
```

#### 記録されるデータ

Bot が以下のコレクションへ記録し、ダッシュボードが参照します。

| コレクション | 内容 | 保持期間 |
| --- | --- | --- |
| `command_logs` | コマンド実行者・サーバー・オプション・成否・エラー種別 | 90日 (TTL) |
| `internal_errors` | エラーコード (UUID7)・発生元・トレースバック・正規化ハッシュ | 180日 (TTL) |
| `bot_status` | 稼働状況のハートビート (30秒間隔)。サーバー数・レイテンシ・実行中クイズ・Lavalink 状態 | 最新のみ |
| `guilds` | 参加サーバー一覧 (名前・人数・参加日) | - |
| `quiz_history` | クイズ1回分の履歴 (参加者・問題数・正解数) | - |
| `bot_state` | メンテナンスモードの状態 | - |

#### メンテナンスモード

- ダッシュボードまたは Bot の `/maintenance` コマンド (オーナー専用) で切り替えられます。
- 有効中は `/play` (コンテキストメニュー含む) がクイズを開始せず、メッセージを返します。実行中のクイズは継続され `/end` で終了できます。
- 設定は MongoDB に保存されるため Bot を再起動しても維持されます。


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
| `DASHBOARD_PORT` | 任意 | ダッシュボードの公開ポート (デフォルト: `8787`。`127.0.0.1` のみに公開) |
| `CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` | ダッシュボード利用時は必須 | Cloudflare Access のチームドメインと AUD タグ |
| `DASHBOARD_ALLOWED_EMAILS` | 任意 | 追加のメールアドレス許可リスト (カンマ区切り) |
| `DASHBOARD_TIMEZONE` | 任意 | 集計に使うタイムゾーン (デフォルト: `Asia/Tokyo`) |
| `DASHBOARD_AUTH_DISABLED` | 任意 | 開発用に認証を無効化 (本番では使用しない) |


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

Spotify や Apple Music など、直接オーディオを取得することができないプラットフォームのURLを使用する場合は、楽曲のメタデータを元に YouTube などのオーディオを取得できるプラットフォームから再生されます。

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

Copyright (C) 2026 Milkeyyy
