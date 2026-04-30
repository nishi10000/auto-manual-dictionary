# 機能仕様

## CLI概要

パッケージ名候補: `auto_manual_dict`

実行例:

```bash
python -m auto_manual_dict ingest --lang ja --input ./manuals/ja --db ./work/dict.sqlite3
python -m auto_manual_dict ingest --lang en --input ./manuals/en --db ./work/dict.sqlite3
python -m auto_manual_dict match-blocks --db ./work/dict.sqlite3
python -m auto_manual_dict match-pages --db ./work/dict.sqlite3
python -m auto_manual_dict extract-terms --db ./work/dict.sqlite3
python -m auto_manual_dict build-concepts --db ./work/dict.sqlite3
python -m auto_manual_dict update-confidence --db ./work/dict.sqlite3
python -m auto_manual_dict export-review --db ./work/dict.sqlite3 --out ./review/review_ready.csv
python -m auto_manual_dict approve --db ./work/dict.sqlite3 --concept-id SYMPTOM_ENGINE_NO_START
python -m auto_manual_dict export-dictionary --db ./work/dict.sqlite3 --format jsonl --out ./dist/dictionary.jsonl
```

## 機能1: ingest

### 入力

- `--lang ja|en`
- `--input` HTMLディレクトリ
- `--db` SQLiteパス

### 処理

- HTMLファイルを再帰的に読む
- ファイルハッシュを計算する
- title / h1-h6 / table / img / a / text を抽出する
- DTC、数値単位、部品番号らしき文字列を抽出する
- ページ特徴量を保存する

### 出力

- `documents`
- `document_features`
- `anchors`

## 機能2: match-pages

### 処理

日本語文書と英語文書の候補対応を作る。ただし 1:1 前提にしない。

対応タイプ:

- `one_to_one`
- `one_to_many`
- `many_to_one`
- `weak_candidate`
- `unmatched`

スコア特徴:

- DTC一致
- 数値単位一致
- 画像名一致
- 表構造類似
- 見出し類似
- アンカー一致
- 本文短縮特徴類似

## 機能3: extract-terms

### 日本語候補

- 連続する漢字/カタカナ/英数字列
- ドメイン辞書に一致する語
- 見出し、表ヘッダ、警告文の名詞句

### 英語候補

- noun phrase風の連続語
- 大文字略語
- DTC/部品/単位周辺の語句

初期は標準ライブラリ正規表現で始める。必要に応じて SudachiPy / spaCy は optional extras とする。

## 機能4: build-concepts

高スコアの `block_match_candidates` 上に出現した日本語/英語の `term_occurrences` を組み合わせ、`concepts` / `concept_terms` / `evidence` に候補として保存する。

MVP挙動:

- 既定では `score >= 0.25` の matched block を使う
- `concept_id` は category と正規化済み日英用語から安定生成する
- `status` は `candidate` のまま。自動で `confirmed` にはしない
- `safe_for_query_expansion` / `safe_for_answer_generation` は人間レビュー前なので 0 のまま
- 再実行しても concept / concept_terms / evidence を重複作成しない

## 機能5: update-confidence

用語候補、ページ候補、断片候補、既存辞書をもとに概念候補の確信度を更新する。

MVPでは `confidence_json` に説明可能な内訳を保存する。

- `anchor_score`
- `section_score`
- `lexical_score`
- `frequency_score`
- `diversity_score`
- `heading_score`
- `table_alignment_score`
- `negative_evidence_penalty`
- `safety_penalty`
- `final_score`

`confidence_version` は `confidence_mvp_0.1`。
`confidence >= 0.85` の候補は `review_ready` にする。ただし `confirmed` はスコアだけでは絶対に設定しない。

スコアを上げる要素:

- 異なるページ/章からの複数証拠
- 異なる証拠タイプの一致
- DTC/トルク/部品番号アンカー
- confirmed辞書との整合

スコアを下げる要素:

- blocked辞書との近さ
- 仕向地/型式/年式差
- LLM推定のみ
- 同一抽出方法からの重複証拠だけ

## 機能6: export-review

`review_ready` 候補をCSV/JSONLで出す。

列:

- concept_id
- ja_terms
- en_terms
- confidence
- evidence_count
- evidence_summary
- sample_ja_context
- sample_en_context
- recommended_action

## 機能7: approve/block

人間レビュー結果を反映する。

- approve: concept/termをconfirmedにする
- block: 危険訳/誤訳をblockedにする
- defer: candidateに戻す
- split: conceptを分割する
- merge: conceptを統合する
