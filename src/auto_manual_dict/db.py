from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "0.1.0"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ingestion_runs (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL UNIQUE,
  lang TEXT NOT NULL CHECK (lang IN ('ja', 'en')),
  input_path TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  documents_seen INTEGER NOT NULL DEFAULT 0,
  documents_inserted INTEGER NOT NULL DEFAULT 0,
  documents_updated INTEGER NOT NULL DEFAULT 0,
  errors INTEGER NOT NULL DEFAULT 0,
  schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  lang TEXT NOT NULL CHECK (lang IN ('ja', 'en')),
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  title TEXT,
  text_excerpt TEXT,
  source_html TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(lang, path)
);

CREATE TABLE IF NOT EXISTS document_blocks (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL,
  block_type TEXT NOT NULL,
  block_index INTEGER NOT NULL,
  heading_path TEXT,
  dom_path TEXT,
  raw_fragment_hash TEXT,
  text TEXT NOT NULL,
  normalized_text TEXT,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  UNIQUE(document_id, block_index)
);

CREATE TABLE IF NOT EXISTS anchors (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL,
  block_id INTEGER,
  anchor_type TEXT NOT NULL,
  value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY(block_id) REFERENCES document_blocks(id) ON DELETE CASCADE,
  UNIQUE(document_id, block_id, anchor_type, normalized_value)
);

CREATE TABLE IF NOT EXISTS block_match_candidates (
  id INTEGER PRIMARY KEY,
  ja_block_id INTEGER NOT NULL,
  en_block_id INTEGER NOT NULL,
  score REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL,
  FOREIGN KEY(ja_block_id) REFERENCES document_blocks(id) ON DELETE CASCADE,
  FOREIGN KEY(en_block_id) REFERENCES document_blocks(id) ON DELETE CASCADE,
  UNIQUE(ja_block_id, en_block_id)
);

CREATE TABLE IF NOT EXISTS page_match_candidates (
  id INTEGER PRIMARY KEY,
  ja_document_id INTEGER NOT NULL,
  en_document_id INTEGER NOT NULL,
  score REAL NOT NULL,
  match_type TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  FOREIGN KEY(ja_document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY(en_document_id) REFERENCES documents(id) ON DELETE CASCADE,
  UNIQUE(ja_document_id, en_document_id)
);

CREATE TABLE IF NOT EXISTS terms (
  id INTEGER PRIMARY KEY,
  lang TEXT NOT NULL CHECK (lang IN ('ja', 'en')),
  term TEXT NOT NULL,
  normalized_term TEXT NOT NULL,
  term_type TEXT,
  status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL,
  UNIQUE(lang, normalized_term)
);

CREATE TABLE IF NOT EXISTS term_occurrences (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL,
  document_id INTEGER NOT NULL,
  block_id INTEGER NOT NULL,
  source TEXT NOT NULL DEFAULT 'block',
  created_at TEXT NOT NULL,
  FOREIGN KEY(term_id) REFERENCES terms(id) ON DELETE CASCADE,
  FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
  FOREIGN KEY(block_id) REFERENCES document_blocks(id) ON DELETE CASCADE,
  UNIQUE(term_id, block_id)
);

CREATE TABLE IF NOT EXISTS concepts (
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

CREATE TABLE IF NOT EXISTS concept_terms (
  concept_id INTEGER NOT NULL,
  term_id INTEGER NOT NULL,
  role TEXT NOT NULL DEFAULT 'label',
  confidence REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'candidate',
  PRIMARY KEY(concept_id, term_id),
  FOREIGN KEY(concept_id) REFERENCES concepts(id),
  FOREIGN KEY(term_id) REFERENCES terms(id)
);

CREATE TABLE IF NOT EXISTS evidence (
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

CREATE TABLE IF NOT EXISTS review_actions (
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

CREATE INDEX IF NOT EXISTS idx_documents_lang ON documents(lang);
CREATE INDEX IF NOT EXISTS idx_anchors_value ON anchors(normalized_value);
CREATE INDEX IF NOT EXISTS idx_terms_lang_norm ON terms(lang, normalized_term);
CREATE INDEX IF NOT EXISTS idx_term_occurrences_term ON term_occurrences(term_id);
CREATE INDEX IF NOT EXISTS idx_term_occurrences_block ON term_occurrences(block_id);
CREATE INDEX IF NOT EXISTS idx_concepts_status_conf ON concepts(status, confidence);
CREATE INDEX IF NOT EXISTS idx_evidence_concept ON evidence(concept_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_matched_block_terms
  ON evidence(concept_id, ja_term_id, en_term_id, ja_block_id, en_block_id, evidence_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_block_match_pair ON block_match_candidates(ja_block_id, en_block_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_page_match_pair ON page_match_candidates(ja_document_id, en_document_id);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_lightweight_migrations(conn: sqlite3.Connection) -> None:
    document_columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    if "source_html" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN source_html TEXT")


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_lightweight_migrations(conn)
