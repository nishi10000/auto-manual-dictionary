# Examples

このディレクトリには、レビューキューと confirmed 辞書のサンプル出力を置いています。

## sample_review.csv

`export-review` が出力するレビュー用CSVの例です。

```bash
python -m auto_manual_dict export-review --db ./work/dict.sqlite3 --out ./review/review_ready.csv
```

人間レビュー担当者は `recommended_action` と evidence/context を見て、必要に応じて `action`, `reviewer`, `reason`, `reason_code`, `review_note` などを編集して `import-review` できます。`row_version` は古いCSV取り込み防止用なので編集しないでください。

取り込み前の検証:

```bash
python -m auto_manual_dict import-review --db ./work/dict.sqlite3 --input ./review/review_ready.csv --dry-run --report ./review/import_report.csv
```

取り込みと結果CSVの書き戻し:

```bash
python -m auto_manual_dict import-review --db ./work/dict.sqlite3 --input ./review/review_ready.csv --write-back ./review/review_imported.csv
```

## sample_dictionary.jsonl

`export-dictionary` が出力する confirmed-only 辞書の例です。

```bash
python -m auto_manual_dict export-dictionary --db ./work/dict.sqlite3 --format jsonl --out ./dist/dictionary.jsonl
```

`export-dictionary` は `status = confirmed` の概念だけを出します。レビュー前の `candidate` / `review_ready` や `blocked` は含めません。

## Safety-specific exports

検索拡張と回答生成では、用途別の安全フラグをさらに確認します。

```bash
python -m auto_manual_dict export-query-expansion --db ./work/dict.sqlite3 --out ./dist/query_expansion.jsonl
python -m auto_manual_dict export-rag-safe --db ./work/dict.sqlite3 --out ./dist/rag_safe.jsonl
```

- `export-query-expansion`: `confirmed` かつ `safe_for_query_expansion = 1`
- `export-rag-safe`: `confirmed` かつ `safe_for_answer_generation = 1`
