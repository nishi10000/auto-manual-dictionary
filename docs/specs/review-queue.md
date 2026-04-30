# レビューキュー仕様

## 目的

日英辞書候補のうち、確信度が閾値を超えたもの、または重要語なのに曖昧なものを、人間が効率よく確認できる形で出力する。

## 出力形式

初期はCSVとJSONL。

```bash
python -m auto_manual_dict export-review --db work.sqlite3 --out review_ready.csv
python -m auto_manual_dict export-review --db work.sqlite3 --format jsonl --out review_ready.jsonl
```

## CSV列

- `concept_id`
- `category`
- `confidence`
- `status`
- `ja_terms`
- `en_terms`
- `evidence_count`
- `evidence_types`
- `sample_ja_context`
- `sample_en_context`
- `anchors`
- `source_files`
- `recommended_action`
- `review_note`

## recommended_action

- `approve`: confirmed化してよさそう
- `inspect`: 文脈確認が必要
- `split`: 複数概念が混ざっている可能性
- `block`: 誤訳/危険訳の可能性

## レビュー操作

```bash
python -m auto_manual_dict approve --db work.sqlite3 --concept-id SYMPTOM_ENGINE_NO_START --reviewer nishihara --reason "文脈と証拠を確認済み"
python -m auto_manual_dict block --db work.sqlite3 --concept-id BAD_TRANSLATION --reviewer nishihara --reason-code wrong_context --reason "文脈違い"
python -m auto_manual_dict defer --db work.sqlite3 --concept-id AMBIGUOUS_TERM --reviewer nishihara --reason "追加証拠待ち"
```

`approve` / `block` / `defer` は `review_actions` に履歴を残す。CSV/JSONLから `import-review` する場合は `row_version` が現在値と一致しない行を stale として拒否する。

## 優先順位

1. 安全・品質に関わる語
2. 検索ログに頻出する語
3. DTC/トルク/警告/診断表周辺
4. confidenceが高い語
5. 多義性が高くsplit候補の語

## 注意

閾値越えだけをレビュー対象にすると、難しい重要語が沈む。したがって `review_ready` 以外にも、重要カテゴリのcandidateをサンプリングして出す。
