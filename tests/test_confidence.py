import json
import sqlite3
from pathlib import Path

from auto_manual_dict.block_matcher import match_blocks
from auto_manual_dict.concepts import build_concepts
from auto_manual_dict.confidence import update_confidence
from auto_manual_dict.ingest import ingest_directory
from auto_manual_dict.term_extract import extract_terms_to_db

FIXTURES = Path(__file__).parent / "fixtures"


def _prepare_db(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)
    match_blocks(db_path=db_path, min_score=0.25, top_k_per_block=3)
    extract_terms_to_db(db_path=db_path)
    build_concepts(db_path=db_path, min_match_score=0.25)
    return db_path


def _concept_for_terms(conn, ja_normalized, en_normalized):
    row = conn.execute(
        """
        SELECT c.*
        FROM concepts c
        JOIN concept_terms ct_ja ON ct_ja.concept_id = c.id
        JOIN terms ja ON ja.id = ct_ja.term_id AND ja.lang = 'ja'
        JOIN concept_terms ct_en ON ct_en.concept_id = c.id
        JOIN terms en ON en.id = ct_en.term_id AND en.lang = 'en'
        WHERE ja.normalized_term = ? AND en.normalized_term = ?
        LIMIT 1
        """,
        (ja_normalized, en_normalized),
    ).fetchone()
    assert row is not None
    return row


def test_update_confidence_stores_explainable_breakdown_and_marks_review_ready(tmp_path):
    db_path = _prepare_db(tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        concept = _concept_for_terms(conn, "エンジンがかからない", "engine does not start")
        evidence = conn.execute("SELECT * FROM evidence WHERE concept_id = ? LIMIT 1", (concept["id"],)).fetchone()
        # Add a second evidence type to prove diversity matters and can push a strong candidate to review_ready.
        conn.execute(
            """
            INSERT INTO evidence(
              concept_id, ja_term_id, en_term_id, ja_document_id, en_document_id,
              ja_block_id, en_block_id, evidence_type, score, extractor_name,
              extractor_version, anchors_json, ja_context, en_context, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'manual_seed_consistency', 0.72,
                    'test', 'test', ?, ?, ?, '2026-01-01T00:00:00+00:00')
            """,
            (
                evidence["concept_id"], evidence["ja_term_id"], evidence["en_term_id"],
                evidence["ja_document_id"], evidence["en_document_id"],
                evidence["ja_block_id"], evidence["en_block_id"],
                evidence["anchors_json"], evidence["ja_context"], evidence["en_context"],
            ),
        )

    result = update_confidence(db_path=db_path, review_ready_threshold=0.85)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        updated = _concept_for_terms(conn, "エンジンがかからない", "engine does not start")
        breakdown = json.loads(updated["confidence_json"])

    assert result.concepts_seen > 0
    assert result.concepts_updated > 0
    assert updated["confidence"] >= 0.85
    assert updated["status"] == "review_ready"
    assert updated["confidence_version"] == "confidence_mvp_0.1"
    assert breakdown["evidence_count"] >= 2
    assert breakdown["evidence_type_count"] >= 2
    assert breakdown["anchor_score"] > 0
    assert breakdown["section_score"] > 0
    assert breakdown["frequency_score"] > 0
    assert breakdown["negative_evidence_penalty"] == 0
    assert breakdown["final_score"] == updated["confidence"]


def test_confirmed_consistency_requires_review_history_before_raising_score(tmp_path):
    db_path = _prepare_db(tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        concept = _concept_for_terms(conn, "エンジンがかからない", "engine does not start")
        evidence = conn.execute("SELECT * FROM evidence WHERE concept_id = ? LIMIT 1", (concept["id"],)).fetchone()
        update_confidence(db_path=db_path, review_ready_threshold=0.85)
        baseline = conn.execute("SELECT confidence FROM concepts WHERE id = ?", (concept["id"],)).fetchone()[0]
        conn.execute(
            """
            INSERT INTO evidence(
              concept_id, ja_term_id, en_term_id, ja_document_id, en_document_id,
              ja_block_id, en_block_id, evidence_type, score,
              extractor_name, extractor_version, ja_context, en_context, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed_consistency', 1.0,
                    'test', 'test', 'unreviewed consistency ja', 'unreviewed consistency en',
                    '2026-01-01T00:00:00+00:00')
            """,
            (
                evidence["concept_id"], evidence["ja_term_id"], evidence["en_term_id"],
                evidence["ja_document_id"], evidence["en_document_id"],
                evidence["ja_block_id"], evidence["en_block_id"],
            ),
        )

    update_confidence(db_path=db_path, review_ready_threshold=0.85)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        updated = _concept_for_terms(conn, "エンジンがかからない", "engine does not start")
        breakdown = json.loads(updated["confidence_json"])

    assert updated["confidence"] == baseline
    assert "confirmed_consistency" not in breakdown["evidence_types"]


def test_negative_evidence_lowers_confidence_and_score_never_confirms(tmp_path):
    db_path = _prepare_db(tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        concept = _concept_for_terms(conn, "燃圧", "fuel pressure")
        evidence = conn.execute("SELECT * FROM evidence WHERE concept_id = ? LIMIT 1", (concept["id"],)).fetchone()
        conn.execute(
            """
            INSERT INTO evidence(
              concept_id, ja_term_id, en_term_id, ja_document_id, en_document_id,
              ja_block_id, en_block_id, evidence_type, score, is_negative_evidence,
              extractor_name, extractor_version, ja_context, en_context, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'blocked_contradiction', 0.95, 1,
                    'test', 'test', 'negative ja', 'negative en', '2026-01-01T00:00:00+00:00')
            """,
            (
                evidence["concept_id"], evidence["ja_term_id"], evidence["en_term_id"],
                evidence["ja_document_id"], evidence["en_document_id"],
                evidence["ja_block_id"], evidence["en_block_id"],
            ),
        )

    update_confidence(db_path=db_path, review_ready_threshold=0.85)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        updated = _concept_for_terms(conn, "燃圧", "fuel pressure")
        breakdown = json.loads(updated["confidence_json"])

    assert breakdown["negative_evidence_penalty"] > 0
    assert updated["confidence"] < 0.85
    assert updated["status"] != "confirmed"


def test_update_confidence_is_idempotent(tmp_path):
    db_path = _prepare_db(tmp_path)

    first = update_confidence(db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        first_rows = conn.execute(
            "SELECT concept_id, confidence, confidence_json, confidence_version, status FROM concepts ORDER BY concept_id"
        ).fetchall()
    second = update_confidence(db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        second_rows = conn.execute(
            "SELECT concept_id, confidence, confidence_json, confidence_version, status FROM concepts ORDER BY concept_id"
        ).fetchall()

    assert first.concepts_seen == second.concepts_seen
    assert first.concepts_updated == second.concepts_updated
    assert len(first_rows) == first.concepts_seen
    assert second_rows == first_rows
