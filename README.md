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

アーティストページのURLなどを使うこともできます。

> 対応しているURL/プラットフォームについては[こちら](#-対応プラットフォームについて)


## 📥 インストール

### ボットを招待

[![Invite Discord Bot](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white&label=Invite)](https://discord.com/oauth2/authorize?client_id=1419676092314161193)

**ボットの稼働状況**

[![Bot Status](https://monitor.milkeyyy.com/api/badge/28/status?style=flat-square&label=Discord%20Bot)](https://status.milkeyyy.com/)

[![Lavalink Status](https://monitor.milkeyyy.com/api/badge/29/status?style=flat-square&label=Lavalink%20Node)](https://status.milkeyyy.com/)


### セルフホスト

> 🚧 工事中 🚧


## 🗨️ サポートなど

### サポート Discord サーバー

ボットに関する質問や不具合報告等は以下の Discord サーバーからお願いします。

[![Support Discord](https://img.shields.io/badge/Discord-%235865F2.svg?style=for-the-badge&logo=discord&logoColor=white&label=Support)](https://discord.gg/bMf9dDjndC)


### 機能要望・不具合報告

機能追加/改善要望や不具合報告は [Issue](https://github.com/Ezolys/MoguTune/issues) を作成したいただけると助かります。


## 🎮 遊び方

### クイズの開始

任意のVCに接続して `/play` コマンドを実行すると、コマンド実行者がその時参加していたVC内のメンバーを参加者としたクイズが開始されます。

解答ボタン等のメッセージは、コマンドを実行したテキストチャンネルに関係なく、コマンド実行者が参加しているVC内のテキストチャットに送信されます。

<img width="1716" height="797" alt="image" src="https://github.com/user-attachments/assets/424b1c31-0a0d-4862-ba30-8048c1014844" />


### 解答

「解答」ボタンを押すと5つの選択肢から楽曲を選択する項目が表示され、楽曲を選択することで解答することができます。

5秒以内に解答できなかった場合は自動的に解答が終了します。

間違えた場合は **お手つき状態** となり、次の人の解答が終わるまで解答できません。

<img width="479" height="300" alt="image" src="https://github.com/user-attachments/assets/663bd280-ad10-46d3-a295-c356ae0fc0da" />

<img width="479" height="484" alt="image" src="https://github.com/user-attachments/assets/34b2f0f7-98d3-4aee-a38b-61586e6d9917" />


### クイズの終了

最後の問題が終わると自動的にクイズが終了し、ランキングが表示されます。

「同じ設定で再度プレイ」ボタンを押すと、同じプレイリスト、同じ出題数で再度クイズを開始することができます。

> `/end` を実行すると、クイズを強制的に終了することができます。この場合、ランキングは終了時点のスコアになります。

<img width="507" height="292" alt="image" src="https://github.com/user-attachments/assets/cf0f0a4e-5243-4a3c-81f2-e6a40cb7edd0" />


### ホストについて

`/play` コマンドを実行したユーザーはクイズの **ホスト** となり、次の問題へ進めたり、問題をスキップすることができます。 ホスト以外のユーザーが問題のスキップなどの操作を行うことはできません。


### 解答の選択肢について

使用するプレイリストのプラットフォームによって、選択肢に表示される楽曲名の表記が異なります。

YouTube のURLを使用した場合、動画のタイトルがそのまま表示されるため、アーティスト名も含まれる場合があります。

ボーカルなどからアーティストを予想し、アーティスト名だけで解答できるのを防ぎたい場合は、YouTube Music や Spotify のURLを使用してください。

> YouTube Music のURLを使用しても、楽曲によってはMVなどのタイトルが表示される場合があります。


## *️⃣ コマンド一覧

> `<>` で囲われたオプションは必須、`[]` で囲われたオプションは任意です。

- `/play <プレイリスト等のURL> [出題数 | デフォルト: 10]`

  クイズを開始します。

  対応しているプレイリストのプラットフォームは Lavalink の設定によって異なります。詳しくは[こちら](#-対応プラットフォームについて)を参照してください。


- `/end`

  クイズを強制的に終了します。正解数などのスコアはコマンドが実行された時点の状態で終了します。


- `/sessions`

  ボットが実行しているクイズの総セッション数を表示します。


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


## 📚 関連リポジトリー

ロジック部分のコードは[こっち](https://github.com/Ezolys/MoguTune-Core)に分離してあります。


## 📜 ライセンス

[MIT License](LICENSE)

Copyright (C) 2026 Milkeyyy
