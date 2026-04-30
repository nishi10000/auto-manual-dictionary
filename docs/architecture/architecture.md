# Python アーキテクチャ

## 方針

Python-only / local-first。まずは標準ライブラリで動く最小構成を作り、必要な依存は optional にする。

## 推奨ディレクトリ

```text
auto-manual-dictionary/
├── pyproject.toml
├── README.md
├── src/
│   └── auto_manual_dict/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── db.py
│       ├── html_extract.py
│       ├── anchors.py
│       ├── features.py
│       ├── page_matcher.py
│       ├── term_extract.py
│       ├── concepts.py
│       ├── confidence.py
│       ├── review.py
│       └── export.py
├── tests/
│   ├── fixtures/
│   │   ├── ja/
│   │   └── en/
│   ├── test_html_extract.py
│   ├── test_anchors.py
│   ├── test_page_matcher.py
│   ├── test_term_extract.py
│   ├── test_confidence.py
│   └── test_review_export.py
├── docs/
└── examples/
```

## モジュール責務

### `cli.py`

- argparseベースCLI
- 各サブコマンドをサービス関数に委譲
- 標準出力に処理件数を表示

### `db.py`

- SQLite接続
- schema作成
- repository関数
- migrationは初期では単一schema SQLでよい

### `html_extract.py`

- HTMLファイルから構造化テキストを抽出
- title/headings/tables/images/links/text_blocks を返す
- 入力HTMLは変更しない

### `anchors.py`

- DTCコード、トルク値、電圧、部品番号、型式などを抽出

### `features.py`

- 文書特徴量を計算
- 見出しsignature、アンカー集合、表形状、画像名集合など

### `page_matcher.py`

- 日英文書候補のスコアリング
- 1:1に固定せず候補集合として保存

### `term_extract.py`

- 日英の用語候補抽出
- 初期はregex中心
- optionalでSudachiPy/spaCyを追加可能

### `concepts.py`

- term候補をconcept候補に束ねる
- concept_id生成
- merge/split補助

### `confidence.py`

- evidenceからconfidence更新
- evidence diversityを重視し、単純な件数だけで上げない

### `review.py`

- review_ready抽出
- approve/block/defer/split/merge操作

### `export.py`

- JSONL/CSV辞書出力
- BM25/RAG用クエリ展開辞書出力

## 依存方針

会社環境では Python と pip が使える前提。したがって、初期実装は標準ライブラリで動く薄い核を保ちつつ、実用性に効くPythonパッケージは導入してよい。

最小:

- Python 3.10+
- sqlite3
- argparse
- html.parser
- pathlib
- csv/json/re/hashlib
- unittest

初期導入候補:

- pandas: レビューCSV、評価レポート、集計
- beautifulsoup4: HTML抽出品質改善
- lxml: HTML/XMLパース高速化
- pytest: テスト実行
- rapidfuzz: 文字列類似度

追加候補:

- scikit-learn: TF-IDF、類似度、評価補助
- sentence-transformers: multilingual embedding
- sudachipy + sudachidict_core: 日本語用語抽出
- spacy: 英語noun phrase抽出

避ける/初期必須にしない:

- 外部DBサーバー必須構成
- Node.js/Java必須ツール
- 外部LLM API必須処理

## 設計原則

- 入力HTMLはimmutableとして扱う
- 候補には必ず根拠を残す
- スコアは再計算可能にする
- LLMは必須にしない
- confirmedも文脈つきで再評価可能にする
