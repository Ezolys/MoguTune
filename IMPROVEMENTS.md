# MoguTune 改善プラン

## Context

MoguTune プロジェクト全体のコード品質、アーキテクチャ、セキュリティを調査し、改善可能な点をまとめる。全体として堅実な構造だが、特に `quiz_session.py`（1524行）の複雑度と重複コードに大きな改善余地がある。

---

## 1. 【高】quiz_session.py の分割・リファクタリング

**現状**: 1524行の巨大ファイルに UI Views、データモデル、セッション管理、ゲームロジックが全て同居。

**改善案**:
- `quiz_session.py` → 以下に分割:
  - `views.py` - Discord UI コンポーネント（QuizReplayButtonView, QuizNextQButtonView, QuizAnswerSelectView, QuizAnswerButtonView）
  - `models.py` - データモデル（QuizPlayer, QuizSession のデータ部分）
  - `quiz_session.py` - セッション管理ロジック（QuizSessionManager + ゲームフロー）

**対象ファイル**: `mogutune/quiz_session.py`

---

## 2. 【高】重複コードの共通化

**現状**: 同じパターンが quiz_session.py 内に5箇所以上繰り返されている。

**改善案**:

### a. トラックタイトル生成（5箇所以上）
```python
# Before: 行221, 240, 419, 1013 等
_title = "Unknown" if _track is None else _track.title if _track.source == "youtube" else _track.title + " - " + _track.author

# After: ヘルパーメソッド化
def _format_track_title(track: mafic.Track | None) -> str: ...
```

### b. セッション検証チェック（4箇所）
行37-58, 90-98, 180-188, 308-316 の重複 → 共通バリデーション関数

### c. プレイヤー一覧テキスト生成（2箇所）
行862-871, 920-929 が同一ロジック → メソッド抽出

### d. オーナー権限チェック（3箇所以上）
```python
if self.session.owner is not None and self.session.owner.id != interaction.user.id:
```
→ `_check_owner(interaction)` メソッドに抽出

**対象ファイル**: `mogutune/quiz_session.py`

---

## 3. 【高】バグ修正

### a. `asyncio.run()` のデッドロックリスク
- **場所**: `quiz_session.py:72`
- **問題**: `__init__` 内で `asyncio.run()` を呼び出しており、既にイベントループが動作中の場合デッドロックする
- **修正**: `asyncio.create_task()` または `asyncio.get_event_loop().create_task()` に変更

### b. kumasan.py の None アクセス
- **場所**: `kumasan.py:59`
- **問題**: 例外発生時に `result` が None でも `result.status_code` にアクセス
- **修正**: None チェック追加

### c. FIXME: 解答判定エラー処理
- **場所**: `quiz_session.py:216`
- **問題**: `answer()` がエラー時も None を返し、不正解判定になる
- **修正**: エラー時は別の処理（再試行またはスキップ）を実装

### d. db.py のエラーログ
- **場所**: `db.py:33`
- **問題**: ループ変数 `e` を出力しているが、これは値であり変数名ではない
- **修正**: 変数名と値の両方をログに出力

---

## 4. 【中】設定の一元管理

**現状**: 環境変数の読み込みが各ファイルに散在し、バリデーションなし。

**改善案**: `config.py` モジュールを新設
- 起動時に全環境変数を読み込み・バリデーション
- 型変換（int, bool）を一箇所で実施
- 未設定の必須変数は即座にエラー
- 分散している以下を統合:
  - Lavalink 設定 (`client.py:38-42`)
  - 音量設定 (`quiz_session.py:505, 508`)
  - 最大セッション数 (`quiz.py:1338`, `general.py:64`)
  - デバッグチャンネル (`client.py:203-206`)
  - SFX パス (`sfx.py:6-9`)

**対象ファイル**: 新規 `mogutune/config.py`、既存の各ファイル

---

## 5. 【中】レースコンディション対策

**現状**: `can_answered` フラグ等の状態が複数コルーチンから同時に参照・変更される可能性。

**改善案**:
- `asyncio.Lock` を導入し、状態変更を排他制御
- 特に `play()`, `raise_hand()`, `answer()` 間の状態遷移を保護
- `NEXT`, `ANSWERED`, `SFX_FINISHED` の Event 操作にもロック適用

**対象ファイル**: `mogutune/quiz_session.py`

---

## 6. 【中】マジックナンバーの定数化

**現状**: 各所にハードコードされた数値。

```python
random.sample(other_tracks, 4)     # → MAX_DUMMY_TRACKS = 4
delete_after=5                     # → ANSWER_DISPLAY_SECONDS = 5
timeout=5.0                        # → ANSWER_TIMEOUT = 5.0
await asyncio.sleep(2)             # → INTER_QUESTION_DELAY = 2
```

**対象ファイル**: `mogutune/quiz_session.py`

---

## 7. 【中】不要な async の除去

**現状**: `QuizPlayer.correct()`, `.incorrect()`, `.incorrect_reset()` が async だが await を使用していない。

**修正**: sync メソッドに変更し、呼び出し元の `await` を削除。

**対象ファイル**: `mogutune/quiz_session.py`

---

## 8. 【中】play() メソッドの分割

**現状**: 235行の巨大メソッド（行806-1041）。

**改善案**: 以下のサブメソッドに分割:
- `_play_question()` - 1問分の再生処理
- `_generate_ranking()` - ランキング計算・表示（行994-1025）
- `_send_end_message()` - 終了メッセージ送信（行1028-1032）
- `_cleanup_messages()` - メッセージ削除処理（行966-977）

**対象ファイル**: `mogutune/quiz_session.py`

---

## 9. 【低】Docker / デプロイ

- `compose.yml` と `application.yml` のデフォルトパスワード `youshallnotpass` にコメント追加（本番変更必須の旨）
- TOKEN のデフォルト空文字列を除去し、未設定時は明示的エラー

**対象ファイル**: `compose.yml`, `mogutune/client.py`

---

## 10. 【低】TODO の解消

- `quiz_session.py:996`: ランキング表示機能の実装（順位付き表示）

---

## 実施優先度まとめ

| 優先度 | 項目 | 効果 |
|--------|------|------|
| 高 | #3 バグ修正 | 安定性向上 |
| 高 | #2 重複コード共通化 | 保守性向上 |
| 高 | #1 ファイル分割 | 可読性・保守性向上 |
| 中 | #4 設定一元管理 | 起動時エラー検出 |
| 中 | #5 レースコンディション | 安定性向上 |
| 中 | #6 マジックナンバー定数化 | 可読性向上 |
| 中 | #7 不要async除去 | コード品質向上 |
| 中 | #8 play()分割 | 可読性向上（#1と併行） |
| 低 | #9 Docker改善 | セキュリティ |
| 低 | #10 TODO解消 | 機能追加 |

## 検証方法

- `ruff check mogutune/ main.py` でリントエラーなし
- `ruff format mogutune/ main.py` でフォーマット適用
- `python main.py` で起動確認（Lavalink/MongoDB 接続含む）
- 各改善後、既存の動作に影響がないことを手動テスト
