# データモデル

## SQLiteテーブル案

## documents

HTMLファイル単位。

```sql
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  lang TEXT NOT NULL CHECK (lang IN ('ja', 'en')),
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  title TEXT,
  text_excerpt TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(lang, path)
);
```

## document_blocks

見出し、段落、表行、警告などの断片。

```sql
CREATE TABLE document_blocks (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL,
  block_type TEXT NOT NULL,
  block_index INTEGER NOT NULL,
  heading_path TEXT,
  dom_path TEXT,
  raw_fragment_hash TEXT,
  text TEXT NOT NULL,
  normalized_text TEXT,
  FOREIGN KEY(document_id) REFERENCES documents(id)
);
```

## anchors

日英で共通しやすい強い手がかり。

```sql
CREATE TABLE anchors (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL,
  block_id INTEGER,
  anchor_type TEXT NOT NULL,
  value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  FOREIGN KEY(document_id) REFERENCES documents(id),
  FOREIGN KEY(block_id) REFERENCES document_blocks(id)
);
```

anchor_type例:

- dtc
- torque
- voltage
- part_number
- model_code
- image_name
- table_shape

## block_match_candidates

日英断片対応候補。非対称HTMLではページ単位よりこちらを中心に扱う。

```sql
CREATE TABLE block_match_candidates (
  id INTEGER PRIMARY KEY,
  ja_block_id INTEGER NOT NULL,
  en_block_id INTEGER NOT NULL,
  score REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL,
  FOREIGN KEY(ja_block_id) REFERENCES document_blocks(id),
  FOREIGN KEY(en_block_id) REFERENCES document_blocks(id)
);
```

## page_match_candidates

日英ページ対応候補。1:1確定ではなく、block/section evidence の補助特徴量として扱う。

```sql
CREATE TABLE page_match_candidates (
  id INTEGER PRIMARY KEY,
  ja_document_id INTEGER NOT NULL,
  en_document_id INTEGER NOT NULL,
  score REAL NOT NULL,
  match_type TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  FOREIGN KEY(ja_document_id) REFERENCES documents(id),
  FOREIGN KEY(en_document_id) REFERENCES documents(id)
);
```

## terms

抽出された用語表現。

```sql
CREATE TABLE terms (
  id INTEGER PRIMARY KEY,
  lang TEXT NOT NULL CHECK (lang IN ('ja', 'en')),
  term TEXT NOT NULL,
  normalized_term TEXT NOT NULL,
  term_type TEXT,
  status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL,
  UNIQUE(lang, normalized_term)
);
```

## concepts

日英表現を束ねる概念。

```sql
CREATE TABLE concepts (
  id INTEGER PRIMARY KEY,
  concept_id TEXT NOT NULL UNIQUE,
  concept_type TEXT,
  category TEXT,
  canonical_label_ja TEXT,
  canonical_label_en TEXT,
  confidence REAL NOT NULL DEFAULT 0,
  confidence_json TEXT,
  confidence_version TEXT,
  status TEXT NOT NULL DEFAULT 'candidate',
  safe_for_query_expansion INTEGER NOT NULL DEFAULT 0,
  safe_for_answer_generation INTEGER NOT NULL DEFAULT 0,
  definition_note TEXT,
  scope_note TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

status:

- candidate
- review_ready
- confirmed
- blocked

## concept_terms

概念と用語の対応。

```sql
CREATE TABLE concept_terms (
  concept_id INTEGER NOT NULL,
  term_id INTEGER NOT NULL,
  role TEXT NOT NULL DEFAULT 'label',
  confidence REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'candidate',
  PRIMARY KEY(concept_id, term_id),
  FOREIGN KEY(concept_id) REFERENCES concepts(id),
  FOREIGN KEY(term_id) REFERENCES terms(id)
);
```

## evidence

候補の根拠。もっとも重要。

```sql
CREATE TABLE evidence (
  id INTEGER PRIMARY KEY,
  concept_id INTEGER,
  ja_term_id INTEGER,
  en_term_id INTEGER,
  ja_document_id INTEGER,
  en_document_id INTEGER,
  ja_block_id INTEGER,
  en_block_id INTEGER,
  evidence_type TEXT NOT NULL,
  score REAL NOT NULL,
  is_negative_evidence INTEGER NOT NULL DEFAULT 0,
  extractor_name TEXT,
  extractor_version TEXT,
  anchors_json TEXT,
  ja_context TEXT,
  en_context TEXT,
  ja_offsets_json TEXT,
  en_offsets_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(concept_id) REFERENCES concepts(id)
);
```

## review_actions

人間レビュー履歴。

```sql
CREATE TABLE review_actions (
  id INTEGER PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  action TEXT NOT NULL,
  previous_status TEXT,
  new_status TEXT,
  reviewer TEXT,
  reason_code TEXT,
  reason TEXT,
  evidence_ids_json TEXT,
  row_version INTEGER,
  created_at TEXT NOT NULL
);
```

## インデックス

```sql
CREATE INDEX idx_documents_lang ON documents(lang);
CREATE INDEX idx_anchors_value ON anchors(normalized_value);
CREATE INDEX idx_terms_lang_norm ON terms(lang, normalized_term);
CREATE INDEX idx_concepts_status_conf ON concepts(status, confidence);
CREATE INDEX idx_evidence_concept ON evidence(concept_id);
```
