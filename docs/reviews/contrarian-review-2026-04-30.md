# 反対意見レビュー 2026-04-30

## Summary

現行案（Python CLI + SQLite + pandas/BeautifulSoup/lxml/rapidfuzz/pytest、概念ID中心辞書、candidate/review_ready/confirmed/blocked）は方向性として妥当。ただし、このまま実装すると「それっぽい対訳辞書」は作れても、安全性が重要な自動車整備マニュアル用の検索/RAG辞書としては弱い。

最大の論点は、ページ対応・確信度・レビュー・証拠管理を雑にすると、誤辞書がBM25/RAG全体を汚染すること。

## Critical Issues / Must Fix

### 1. ページ対応を中心に置きすぎる危険

日英HTMLはファイル名もページ数も一致せず、内容も完全対訳ではない。`page_matcher` を中心に設計すると、ページ対応ミスが用語候補・概念統合・confidenceへ連鎖する。

対応:

- ページ対応は補助特徴量に下げる。
- block/section/evidence 中心にする。
- `document_blocks` に section_path / heading_hierarchy / block_type / DOM path / raw fragment hash を持たせる。
- `block_alignment_candidates` のような断片対応候補を第一級にする。

### 2. concept_id の生成・統合ルールが曖昧

概念ID中心辞書はよいが、何を同一概念にするかが曖昧だと、過剰マージ/過剰分割が起きる。

対応:

- `concept_type` を持つ: part / fluid / warning / operation / indicator / system / procedure / spec / symptom / other
- `canonical_label_ja`, `canonical_label_en`, `definition_note`, `scope_note` を持つ。
- `concept_terms` に term_role を持つ: preferred / synonym / abbreviation / spelling_variant / deprecated / context_only
- confirmedでも `safe_for_query_expansion` と `safe_for_answer_generation` を分ける。

### 3. confirmed と RAG-safe を分離すべき

`confirmed` は「人間が用語対応を確認した」という意味であり、検索展開や回答生成に使ってよい保証とは別。

対応:

- `confirmed_safe_for_search`
- `confirmed_safe_for_answering`
- `safe_for_query_expansion`
- `safe_for_answer_generation`

を概念または concept_terms に持たせる。

### 4. evidence設計がまだ弱い

このプロジェクトの価値は、用語ペアそのものより「なぜそう判断したか」の証拠にある。証拠が弱いとレビュー不能になる。

対応:

- evidence に source/target block id、snippet、offset、extractor version、negative flag、review visibility を持たせる。
- `is_negative_evidence` を入れる。
- evidence_type を細分化する: anchor_match / heading_similarity / table_alignment / paragraph_alignment / neighbor_terms / human_review / blocked_contradiction など。

### 5. confidenceスコアがブラックボックス化する危険

単一の `confidence=0.82` だけでは、人間が信用できない。証拠数が多くても同じ誤抽出が繰り返されただけの可能性がある。

対応:

- confidence breakdown を保存する。
  - anchor_score
  - heading_score
  - section_score
  - lexical_score
  - frequency_score
  - table_alignment_score
  - negative_evidence_penalty
  - safety_penalty
- `confidence_version` を保存する。
- review_ready昇格条件を明文化する。
- confirmedへの遷移は人間レビューのみ。

### 6. CSVレビューの競合・履歴設計が不足

CSVレビューは実務的だが、古いCSV、複数人レビュー、Excel文字化け、自動変換、row競合が起きる。

対応:

- review item id
- row_version
- export_batch_id
- exported_at
- evidence_ids
- current_status
- reviewer_decision
- reason_code
- reviewer_note

をCSVに含める。

Import時は row_version mismatch を拒否する。

### 7. 機密HTMLの扱いを明文化すべき

会社の整備マニュアルHTMLは機密の可能性が高い。設計資料にローカル処理・ログ制御・外部送信禁止を明記するべき。

対応:

- 外部API送信禁止をデフォルトにする。
- ログに本文全文を出さない。
- エラー時にHTML断片を漏らさない。
- SQLite/CSV出力先を明示指定させる。
- 一時ファイル削除方針を持つ。
- export manifest と checksum を残す。

### 8. warning/caution/note/negative instruction を特別扱いすべき

自動車整備マニュアルでは、警告・注意・禁止・必ず・Do not/Never などが非常に重要。通常本文と同じ扱いにすると危険。

対応:

- block_type に warning/caution/note/prohibition/procedure/table を持つ。
- negative instruction detection を入れる。
- safety blockは通常本文より高優先度で保持・レビューする。

## Missing Requirements

### 1. ingestion_runs / source_files / export_manifest

再現性のため、処理単位を保存する。

追加候補:

- `ingestion_runs`: run_id, config_hash, tool_versions, started_at
- `source_files`: path, sha256, file_size, lang, manual_id, version
- `dictionary_exports`: export_id, format, filters, row_count, checksum

### 2. concept relationships

概念同士の関係が必要になる。

例:

- broader/narrower
- related
- conflicts_with
- parent/child

### 3. 正規化仕様

日本語・英語・単位・記号の正規化を先に決める。

最低限:

- Unicode NFKC
- 全角/半角
- 大文字小文字
- ハイフン/ダッシュ
- 長音
- スペース
- 単位表記
- 括弧
- HTML entity

### 4. gold set / regression fixture

辞書品質はTDDだけでは測れない。小さな正解セットが必要。

評価指標:

- candidate precision
- confirmed precision
- false merge rate
- false split rate
- unsafe expansion rate
- reviewer workload per confirmed concept

## Suggested Implementation Order Change

現行の実装計画では `page_matcher` が早めに来ているが、より安全には以下。

1. schema + migrations
2. source file ingestion with checksum
3. HTML block extraction with stable IDs
4. normalization
5. anchor/heading/table/safety block extraction
6. block/section candidate evidence generation
7. page candidate generation（補助）
8. term extraction
9. concept candidate creation
10. confidence breakdown
11. review CSV export/import with row_version
12. confirmed dictionary export
13. gold-set regression tests

## Anti-patterns to Avoid

- ページ番号一致を強い証拠として扱う
- confirmed をスコア閾値だけで自動設定する
- 日本語termsを単純n-gramだけで作る
- CSVレビューでevidenceを見せない
- blocked理由を保存しない
- 抽出ルールのversionを保存しない
- RAG用辞書とレビュー用辞書を同一視する
- warning/caution/noteを通常本文と同じ重みで扱う
- source HTML本文をログに大量出力する
- 再取り込み時の重複・更新・削除ポリシーを後回しにする

## Decision

実装前に設計を以下へ修正する。

- ページ中心から block/section/evidence 中心へ
- confirmed と RAG/search safe を分離
- evidence と confidence を説明可能にする
- CSVレビューに row_version / export_batch_id / evidence_ids を入れる
- 機密HTMLのローカル処理・ログ制御を明文化
- safety block / negative instruction を特別扱い
