# 実運用ワークフロー

## 目的

Auto Manual Dictionary を実務で使うときの手順と、人間が確認するポイントを定義する。

## 全体像

人間が全ページを読むのではなく、システムがHTMLから候補と根拠を集め、人間は危険度・確信度・影響度の高い候補だけを見る。

基本サイクル:

1. 日英HTMLを投入する
2. HTMLを解析して block / section / table / warning / anchor を抽出する
3. 日英の断片対応候補を作る
4. 用語候補・概念候補を作る
5. evidence と confidence を更新する
6. review_ready をCSV/HTMLで出す
7. 人間が承認・修正・保留・ブロックする
8. confirmed かつ safe なものだけを検索/RAG辞書に出す
9. 新しいHTMLを追加して再実行する

## 操作手順

### 1. データ投入

```bash
python -m auto_manual_dict ingest --lang ja --input ./manuals/ja --db ./work/dict.sqlite3
python -m auto_manual_dict ingest --lang en --input ./manuals/en --db ./work/dict.sqlite3
```

システムが行うこと:

- HTMLファイルのパス、サイズ、sha256を保存
- 見出し、本文、表、画像、リンク、警告、注意、手順を抽出
- DTC、トルク値、電圧、部品番号、画像名などのanchorを抽出

人間が見るもの:

- 通常は見ない
- 取り込み件数、失敗件数、極端に短い/長い抽出結果だけ確認する

### 2. 候補生成

```bash
python -m auto_manual_dict match-blocks --db ./work/dict.sqlite3
python -m auto_manual_dict extract-terms --db ./work/dict.sqlite3
python -m auto_manual_dict build-concepts --db ./work/dict.sqlite3
python -m auto_manual_dict update-confidence --db ./work/dict.sqlite3
```

システムが行うこと:

- 日英のblock/section対応候補を作る
- 用語候補を抽出する
- 概念ID候補に束ねる
- evidenceを追加する
- confidenceと内訳を更新する

人間が見るもの:

- 通常は見ない
- 初期導入時だけ、上位候補のサンプルを見て抽出が壊れていないか確認する

### 3. レビューキュー出力

```bash
python -m auto_manual_dict export-review --db ./work/dict.sqlite3 --out ./review/review_ready.csv
```

人間が見るもの:

- `review_ready` 候補
- 高confidence候補
- 低confidenceだが重要/危険な候補
- blocked候補の再発
- warning/caution/note/prohibitionに関係する候補

CSV/HTMLに出すべき項目:

- review_item_id
- concept_id
- concept_type
- 日本語候補語
- 英語候補語
- confidence
- confidence breakdown
- status
- safe_for_query_expansion
- safe_for_answer_generation
- evidence summary
- evidence_ids
- 日本語snippet
- 英語snippet
- 出典HTMLパス
- 見出しパス
- anchor一致: DTC、トルク、部品番号、画像名など
- negative evidence / caution
- 推奨アクション
- reviewer_decision
- reviewer_note
- reason_code
- row_version
- export_batch_id

### 4. 人間レビュー

人間は候補ごとに以下を見る。

#### A. 用語対応は正しいか

例:

- `始動不良` = `engine does not start` は妥当か
- `補機バッテリー` = `auxiliary battery` は妥当か
- `学習` = `learning` なのか `calibration` なのか

判断:

- approve
- edit
- hold
- block

#### B. 概念の粒度は正しいか

見る点:

- 広すぎないか
- 狭すぎないか
- 別概念を混ぜていないか
- 親子関係にすべきか

例:

- `brake` と `parking brake` は同一にしない
- `warning light` と `indicator light` は文脈によって分ける

#### C. 検索展開に使ってよいか

用語対応が正しくても、検索展開に使うとノイズになることがある。

見る点:

- 同義語として広げてよいか
- 型式/章/作業文脈に限定すべきか
- BM25で検索結果を汚さないか

判断:

- `safe_for_query_expansion = yes/no`

#### D. RAG回答生成に使ってよいか

検索補助よりさらに慎重に判断する。

見る点:

- 整備作業の指示文に使ってよいか
- 警告/注意/禁止の意味を壊さないか
- 誤訳時の危険が大きくないか

判断:

- `safe_for_answer_generation = yes/no`

#### E. 証拠は十分か

見る点:

- DTCやトルク値など強いanchorがあるか
- 同じ章/表/手順で対応しているか
- 複数ソースから独立した証拠があるか
- 逆に矛盾する証拠がないか

### 5. レビュー反映

```bash
python -m auto_manual_dict import-review --db ./work/dict.sqlite3 --input ./review/review_ready_edited.csv
```

システムが行うこと:

- row_versionを確認
- 古いCSVなら拒否
- reviewer、reason_code、noteを保存
- statusを更新
- blockedを今後の候補生成で減点/除外

### 6. 辞書出力

```bash
python -m auto_manual_dict export-dictionary --db ./work/dict.sqlite3 --format jsonl --out ./dist/concepts.jsonl
python -m auto_manual_dict export-query-expansion --db ./work/dict.sqlite3 --out ./dist/query_expansion.jsonl
python -m auto_manual_dict export-rag-safe --db ./work/dict.sqlite3 --out ./dist/rag_safe_dictionary.jsonl
```

出力の使い分け:

- `concepts.jsonl`: 全体の概念辞書
- `query_expansion.jsonl`: BM25/検索展開用。`safe_for_query_expansion` のみ
- `rag_safe_dictionary.jsonl`: 回答生成補助用。`safe_for_answer_generation` のみ
- `blocked_terms.csv`: 誤訳・危険訳の監視用

## 人間が見るべき優先順位

### 最優先

- warning / caution / note / prohibition に関係する候補
- トルク値、電圧、締付、エアバッグ、ブレーキ、高電圧、燃料、火災、感電に関係する候補
- confidenceは高いがnegative evidenceもある候補
- 検索展開に使う予定の候補
- RAG回答生成に使う予定の候補

### 次に見る

- confidenceが閾値を超えた候補
- 複数HTML/複数章で繰り返し出る候補
- 頻出語で検索品質に影響が大きい候補
- blocked候補と似た候補

### 後回しでよい

- candidateで証拠が少ない候補
- 固有の一箇所にしか出ない候補
- 検索展開にも回答生成にも使わない候補

## レビュー判断の種類

### approve

用語対応・概念粒度が正しい。

必要なら以下を指定する:

- safe_for_query_expansion
- safe_for_answer_generation
- scope_note

### edit

候補は近いが修正が必要。

例:

- 日本語ラベルを変更
- 英語ラベルを変更
- synonymではなくcontext_onlyに変更
- conceptを分割/統合する

### hold

判断保留。

理由例:

- 証拠不足
- 文脈依存
- 専門家確認待ち
- 実車種/仕向地情報が必要

### block

誤訳・危険訳・検索展開に使うべきでない候補。

理由例:

- wrong_translation
- too_broad
- too_narrow
- safety_risk
- context_mismatch
- insufficient_evidence
- duplicate_or_merge_error

## 実務での運用リズム

### 初期導入

- まず小さいHTMLセットで回す
- レビューCSVを見て、抽出・正規化・confidence式を調整する
- 20〜50件ほど手レビューして、レビュー画面/CSV項目が足りるか確認する

### 通常運用

- 新しい日英HTMLを追加
- ingest/updateを実行
- review_readyだけ確認
- confirmed/safe辞書を出力
- 検索/RAG側に反映

### 定期メンテ

- blocked理由の多いパターンを確認
- confidence閾値を調整
- false merge / false split を確認
- query expansionで検索品質が落ちていないか確認

## 重要な考え方

人間は「全候補を翻訳チェックする人」ではなく、システムが集めた証拠を見て、危険な候補・影響が大きい候補・検索に使う候補だけを承認するレビュアーになる。

最終的な運用目標は、読む量を減らしながら、誤辞書が検索/RAGに混入するリスクを下げること。
