# Auto Manual Dictionary Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a Python-only CLI that ingests asymmetric Japanese/English automotive manual HTML and grows a concept-centered multilingual terminology dictionary with evidence, confidence, and human review workflow.

**Architecture:** Local-first Python package using SQLite for persistence. HTML is parsed into documents, blocks, anchors, features, page match candidates, term candidates, concept candidates, evidence, and review actions. No external service is required for the MVP.

**Tech Stack:** Python 3.10+, argparse, sqlite3, pathlib, BeautifulSoup4/lxml for HTML parsing, pandas for review/evaluation tables, rapidfuzz for string similarity, pytest/unittest for tests. Optional later: scikit-learn, sentence-transformers, SudachiPy, spaCy.

---

## Task 1: Create Python package skeleton

**Objective:** Create the basic src-layout Python package and CLI entry point.

**Files:**
- Create: `pyproject.toml`
- Create: `src/auto_manual_dict/__init__.py`
- Create: `src/auto_manual_dict/__main__.py`
- Create: `src/auto_manual_dict/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write failing test**

```python
import unittest
from auto_manual_dict.cli import build_parser

class TestCli(unittest.TestCase):
    def test_parser_has_ingest_command(self):
        parser = build_parser()
        args = parser.parse_args(["ingest", "--lang", "ja", "--input", "manuals/ja", "--db", "work.sqlite3"])
        self.assertEqual(args.command, "ingest")
        self.assertEqual(args.lang, "ja")
```

**Step 2: Run test to verify failure**

Run:

```bash
python -m unittest tests.test_cli -v
```

Expected: FAIL because package or `build_parser` does not exist.

**Step 3: Minimal implementation**

Implement argparse parser with subcommands: `ingest`, `match-pages`, `extract-terms`, `update-confidence`, `export-review`, `approve`, `block`, `export-dictionary`.

**Step 4: Run test**

```bash
python -m unittest tests.test_cli -v
```

Expected: PASS.

---

## Task 2: Create SQLite schema

**Objective:** Initialize the database schema.

**Files:**
- Create: `src/auto_manual_dict/db.py`
- Test: `tests/test_db.py`

**Test behavior:**

- `init_db(path)` creates tables:
  - documents
  - document_blocks
  - anchors
  - page_match_candidates
  - terms
  - concepts
  - concept_terms
  - evidence
  - review_actions

**Verification:**

```bash
python -m unittest tests.test_db -v
```

---

## Task 3: Implement HTML extraction

**Objective:** Extract title, headings, text blocks, tables, images, and links from HTML.

**Files:**
- Create: `src/auto_manual_dict/html_extract.py`
- Create fixtures: `tests/fixtures/ja/basic.html`
- Test: `tests/test_html_extract.py`

**Test cases:**

- Extract title
- Extract h1/h2 in order
- Extract paragraphs
- Extract table text without dropping cells
- Extract image src/alt
- Detect warning/caution/note/prohibition/procedure blocks when visible in markup/text
- Ignore script/style
- Do not log full source HTML or confidential large text snippets on parse errors

**Verification:**

```bash
python -m unittest tests.test_html_extract -v
```

---

## Task 4: Implement anchor extraction

**Objective:** Extract strong cross-lingual anchors.

**Files:**
- Create: `src/auto_manual_dict/anchors.py`
- Test: `tests/test_anchors.py`

**Test cases:**

- `P0A80` -> dtc
- `216 N·m`, `216 Nm`, `216 N m` -> torque normalized
- `12 V` -> voltage
- image file names -> image_name
- duplicate anchors removed

**Verification:**

```bash
python -m unittest tests.test_anchors -v
```

---

## Task 5: Implement ingest command service

**Objective:** Read HTML files recursively and store documents, blocks, anchors.

**Files:**
- Create: `src/auto_manual_dict/ingest.py`
- Modify: `src/auto_manual_dict/cli.py`
- Test: `tests/test_ingest.py`

**Test behavior:**

- Ingest two fixture HTML files
- Verify documents count
- Verify blocks count
- Verify anchors count
- Re-ingest same files should not duplicate documents

**Verification:**

```bash
python -m unittest tests.test_ingest -v
```

---

## Task 6: Implement block/section evidence matching

**Objective:** Score Japanese/English block or section candidate pairs without assuming page-level 1:1 alignment. Page matching is treated as a supplementary feature, not the main truth source.

**Files:**
- Create: `src/auto_manual_dict/block_matcher.py`
- Create: `src/auto_manual_dict/page_matcher.py`
- Test: `tests/test_block_matcher.py`
- Test: `tests/test_page_matcher.py`

**Scoring MVP:**

- shared DTC: strong +0.35
- shared torque/voltage/part number: strong +0.25
- shared image name: +0.20
- heading token overlap: +0.10
- table shape similarity: +0.10

Clamp score to 0..1.

**Test behavior:**

- DTC+torque pair scores higher than unrelated pair
- one Japanese page can produce multiple English candidates
- unmatched pages remain below threshold

---

## Task 7: Implement term extraction

**Objective:** Extract Japanese and English term candidates from headings and blocks.

**Files:**
- Create: `src/auto_manual_dict/term_extract.py`
- Test: `tests/test_term_extract.py`

**MVP Japanese regex:**

- sequences of Kanji/Katakana/ASCII around automotive terms
- preserve terms like `締付トルク`, `始動不良`, `補機バッテリー`

**MVP English regex:**

- noun phrase-like 1-4 word sequences
- preserve `tightening torque`, `engine does not start`, `fuel pressure`

---

## Task 8: Implement concept candidate creation

**Objective:** Group term candidates into concept candidates with evidence.

**Files:**
- Create: `src/auto_manual_dict/concepts.py`
- Test: `tests/test_concepts.py`

**Behavior:**

- If ja/en terms appear in high-scoring matched blocks, create or update concept
- Generate stable concept_id from category and normalized terms when unknown
- Store evidence rows with contexts

---

## Task 9: Implement confidence scoring

**Objective:** Update concept confidence using evidence diversity, not only evidence count.

**Files:**
- Create: `src/auto_manual_dict/confidence.py`
- Test: `tests/test_confidence.py`

**Behavior:**

- Multiple evidence types raise score more than repeated same evidence
- Store confidence breakdown such as anchor_score, heading_score, section_score, lexical_score, frequency_score, table_alignment_score, negative_evidence_penalty, safety_penalty
- Store confidence_version with every update
- blocked contradiction lowers score
- confirmed consistency raises score only when review history allows it
- threshold >= 0.85 changes status to `review_ready`
- `confirmed` is never set by score alone; it requires explicit human review action

---

## Task 10: Implement review export and actions

**Objective:** Export review queue and support approve/block/defer actions.

**Files:**
- Create: `src/auto_manual_dict/review.py`
- Create: `src/auto_manual_dict/export.py`
- Test: `tests/test_review_export.py`

**Behavior:**

- Export only `review_ready` concepts by default
- CSV includes concept_id, terms, confidence, confidence breakdown, evidence ids, evidence summary, sample contexts, current status, row_version, export_batch_id
- approve changes status to confirmed only with reviewer and reason
- block changes status to blocked only with reason_code
- import rejects row_version mismatch to avoid stale CSV overwrites
- confirmed-only dictionary export excludes candidate/review_ready/blocked
- query expansion export includes only terms marked safe_for_query_expansion
- answer-generation export includes only terms marked safe_for_answer_generation

---

## Task 11: End-to-end fixture test

**Objective:** Verify full CLI flow on tiny asymmetric HTML corpus.

**Files:**
- Create fixtures:
  - `tests/fixtures/ja/no_start.html`
  - `tests/fixtures/en/engine_no_start_a.html`
  - `tests/fixtures/en/engine_no_start_b.html`
- Test: `tests/test_e2e.py`

**Flow:**

```bash
python -m auto_manual_dict ingest --lang ja --input tests/fixtures/ja --db /tmp/test.sqlite3
python -m auto_manual_dict ingest --lang en --input tests/fixtures/en --db /tmp/test.sqlite3
python -m auto_manual_dict match-pages --db /tmp/test.sqlite3
python -m auto_manual_dict extract-terms --db /tmp/test.sqlite3
python -m auto_manual_dict update-confidence --db /tmp/test.sqlite3
python -m auto_manual_dict export-review --db /tmp/test.sqlite3 --out /tmp/review.csv
```

Expected:

- No command fails
- Review CSV contains at least one candidate around `始動不良` / `engine does not start`

---

## Task 12: Documentation and examples

**Objective:** Add user-facing README and example commands.

**Files:**
- Modify: `README.md`
- Create: `examples/README.md`
- Create: `examples/sample_review.csv`
- Create: `examples/sample_dictionary.jsonl`

**Verification:**

Run all tests:

```bash
python -m unittest discover -s tests -v
```

Expected: all tests pass.
