# ADR 0001: Python-only / Local-first 構成にする

## Status

Accepted

## Context

会社環境では Python しか動かない。自動車整備マニュアルHTMLから日英辞書を作るには、HTML解析、特徴抽出、候補生成、レビュー、SQLite保存、CSV/JSONL出力が必要だが、Node.js / Java / 外部DBに依存すると導入が難しい。

## Decision

初期プロジェクトは Python-only / local-first とする。

- 実行形式: Python CLI
- 保存: SQLite 標準ライブラリ `sqlite3`
- 入出力: ローカルHTML、JSONL、CSV
- HTML解析: Pythonライブラリ（標準 `html.parser` から開始、必要に応じて BeautifulSoup/lxml を導入）
- データ処理: pip は使えるため pandas / numpy / scikit-learn / rapidfuzz などは必要に応じて導入可能
- テスト: pytest を推奨。pytest が入れられない環境では unittest にフォールバック。
- Web UIは初期スコープ外。レビューキューはCSV/JSONL/HTMLレポートで出力。

## Consequences

良い点:

- 会社環境で動かしやすい
- 外部サービスなしで検証できる
- 機密マニュアルを外に出さずに済む
- CIなしでもローカルテストしやすい

悪い点:

- 高度な検索基盤（OpenSearch等）は初期では使わない
- 大規模データでは性能限界がある
- GUIレビュー体験は後回し

## Follow-up

必要になったら optional backend として以下を追加する。

- SQLite FTS5
- sentence-transformers embedding
- scikit-learn TF-IDF
- Streamlit/FlaskのローカルレビューUI
