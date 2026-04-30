# Auto Manual Dictionary

自動車整備マニュアルの日本語/英語HTMLから、検索・RAGに使えるレビュー済み多言語用語辞書を育てる Python + SQLite のローカルCLIです。

## 目的

整備マニュアルは日英でページ数・章立て・ファイル名が一致しないことがあります。このプロジェクトは 1:1 対応を前提にせず、HTMLから以下を段階的に抽出します。

- 文書・ブロック・見出し・表・注意文
- DTC、数値単位、画像名などのアンカー
- ページ/ブロック対応候補
- 日英用語候補
- 概念ID中心の辞書候補
- confidence と evidence
- 人間レビュー済みの confirmed 辞書

初期方針は **Python-only / local-first** です。Node.js、Java、外部DBサーバーは不要です。

## 前提

- Python が使えること
- SQLite は Python 標準ライブラリの `sqlite3` を利用
- 入力はローカルHTMLディレクトリ
- 出力は SQLite / CSV / JSONL

## セットアップ

```bash
git clone https://github.com/nishi10000/auto-manual-dictionary.git
cd auto-manual-dictionary
python -m pip install -e .
```

開発時は pytest を入れてください。

```bash
python -m pip install pytest
python -m pytest tests/ -q
```

## Quickstart: fixtureで一通り実行

```bash
DB=./work/dict.sqlite3
mkdir -p ./work ./review ./dist

python -m auto_manual_dict ingest --lang ja --input tests/fixtures/ja --db "$DB"
python -m auto_manual_dict ingest --lang en --input tests/fixtures/en --db "$DB"
python -m auto_manual_dict match-pages --db "$DB"
python -m auto_manual_dict match-blocks --db "$DB"
python -m auto_manual_dict extract-terms --db "$DB"
python -m auto_manual_dict build-concepts --db "$DB"
python -m auto_manual_dict update-confidence --db "$DB" --review-ready-threshold 0.40
python -m auto_manual_dict export-review --db "$DB" --out ./review/review_ready.csv
```

`--review-ready-threshold 0.40` は小さなfixtureでレビュー候補を出すためのQA用例です。通常運用の既定値は `0.85` です。

## 人間レビュー

レビューCSVを確認し、conceptごとに approve / block / defer を実行します。

```bash
python -m auto_manual_dict approve \
  --db "$DB" \
  --concept-id concept:unknown:example \
  --reviewer nishihara \
  --reason "文脈と証拠を確認済み"

python -m auto_manual_dict block \
  --db "$DB" \
  --concept-id concept:unknown:bad-example \
  --reviewer nishihara \
  --reason-code wrong_context \
  --reason "文脈違い"

python -m auto_manual_dict defer \
  --db "$DB" \
  --concept-id concept:unknown:ambiguous-example \
  --reviewer nishihara \
  --reason "追加証拠待ち"
```

CSV/JSONLでまとめて取り込む場合:

```bash
python -m auto_manual_dict import-review --db "$DB" --input ./review/review_ready.csv
```

取り込み前に検証だけ行う場合:

```bash
python -m auto_manual_dict import-review \
  --db "$DB" \
  --input ./review/review_ready.csv \
  --dry-run \
  --report ./review/import_report.csv
```

取り込み結果をCSVに書き戻す場合:

```bash
python -m auto_manual_dict import-review \
  --db "$DB" \
  --input ./review/review_ready.csv \
  --write-back ./review/review_imported.csv
```

`import-review` は取り込み前に全行を検証し、エラーがある場合は一部だけ反映することを避けます。`row_version` が現在値と違う行は stale CSV として拒否します。

レビューCSVで人間が主に編集する列:

- `action`: `approve` / `block` / `defer` / `inspect`
  - `approve`: 確認済みとして `confirmed` にする
  - `block`: 誤対応・危険・文脈違いとして `blocked` にする
  - `defer`: 追加確認待ちとして `candidate` に戻す
  - `inspect`: 何も反映せずスキップ
- `reviewer`: レビュー担当者名。`approve` / `block` / `defer` では必須
- `reason`: 判断理由。`approve` / `defer` では必須
- `reason_code`: `block` の機械可読な理由コード。例: `wrong_context`, `unsafe_mismatch`, `duplicate`
- `review_note`: レビュー中のメモ。`reason` が空の場合は理由として利用できます
- `row_version`: 編集しないでください。古いCSVによる上書きを防ぐための値です
- `recommended_action`: システム推奨です。必要に応じて `action` にコピーして使います

## 辞書出力

confirmed だけを辞書として出します。

```bash
python -m auto_manual_dict export-dictionary --db "$DB" --format jsonl --out ./dist/dictionary.jsonl
```

安全フラグ付きの用途別出力:

```bash
python -m auto_manual_dict export-query-expansion --db "$DB" --out ./dist/query_expansion.jsonl
python -m auto_manual_dict export-rag-safe --db "$DB" --out ./dist/rag_safe.jsonl
```

## 安全ポリシー

- 自動生成した概念候補は `candidate` または `review_ready` のままです。
- `confirmed` は人間の `approve` action でのみ設定します。
- 自動生成時点では以下の安全フラグは 0 です。
  - `safe_for_query_expansion`
  - `safe_for_answer_generation`
- `export-dictionary` は `confirmed` のみ出力します。
- `export-query-expansion` は `confirmed` かつ `safe_for_query_expansion = 1` のみ出力します。
- `export-rag-safe` は `confirmed` かつ `safe_for_answer_generation = 1` のみ出力します。

## 機密データの扱い

SQLite DB と review CSV / import report / write-back CSV には、マニュアル由来の本文断片、ファイルパス、証拠contextが含まれることがあります。社外共有や公開リポジトリへのコミットは避け、必要な場合は `dist/` の confirmed 辞書だけを用途に応じて共有してください。

## 主なコマンド

- `ingest`: HTMLを読み、documents / blocks / anchors をSQLiteに保存
- `match-pages`: 日英ページ対応候補を保存
- `match-blocks`: 日英ブロック対応候補を保存
- `extract-terms`: 日英用語候補と出現箇所を保存
- `build-concepts`: 用語候補と対応ブロックから概念候補を作成
- `update-confidence`: evidenceからconfidenceとreview_ready状態を更新
- `export-review`: review_ready候補をCSV/JSONL出力
- `approve` / `block` / `defer`: 人間レビュー結果を反映
- `import-review`: CSV/JSONLのレビュー結果を取り込み。`--dry-run`, `--report`, `--write-back` 対応
- `export-dictionary`: confirmed-only辞書を出力

## examples

サンプル出力は `examples/` を参照してください。

- `examples/README.md`
- `examples/sample_review.csv`
- `examples/sample_dictionary.jsonl`

## 主要ドキュメント

- `docs/specs/requirements.md` — 要件定義
- `docs/specs/functional-spec.md` — 機能仕様
- `docs/specs/operations-workflow.md` — 実運用手順と人間レビュー対象
- `docs/architecture/architecture.md` — Pythonアーキテクチャ
- `docs/architecture/data-model.md` — SQLite/JSONデータモデル
- `docs/testing/test-strategy.md` — テスト設計
- `docs/plans/implementation-plan.md` — TDD前提の実装計画

## 制限

- MVPの用語抽出は標準ライブラリ中心の軽量実装です。
- confidence scoring は説明可能性を優先した初期版です。
- 実運用では review CSV を人間が確認し、重要語から段階的に confirmed 化してください。
