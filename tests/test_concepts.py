import sqlite3
from pathlib import Path

from auto_manual_dict.block_matcher import match_blocks
from auto_manual_dict.concepts import build_concepts
from auto_manual_dict.ingest import ingest_directory
from auto_manual_dict.term_extract import extract_terms_to_db

FIXTURES = Path(__file__).parent / "fixtures"


def _prepare_db(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)
    match_blocks(db_path=db_path, min_score=0.25, top_k_per_block=3)
    extract_terms_to_db(db_path=db_path)
    return db_path


def test_build_concepts_groups_terms_from_high_scoring_matched_blocks_with_evidence(tmp_path):
    db_path = _prepare_db(tmp_path)

    result = build_concepts(db_path=db_path, min_match_score=0.25)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT c.concept_id, c.status, c.canonical_label_ja, c.canonical_label_en,
                   c.safe_for_query_expansion, c.safe_for_answer_generation,
                   e.score, e.evidence_type, e.ja_context, e.en_context
            FROM concepts c
            JOIN concept_terms ct_ja ON ct_ja.concept_id = c.id
            JOIN terms ja ON ja.id = ct_ja.term_id AND ja.lang = 'ja'
            JOIN concept_terms ct_en ON ct_en.concept_id = c.id
            JOIN terms en ON en.id = ct_en.term_id AND en.lang = 'en'
            JOIN evidence e ON e.concept_id = c.id
            WHERE ja.normalized_term = 'エンジンがかからない'
              AND en.normalized_term = 'engine does not start'
            ORDER BY e.score DESC
            LIMIT 1
            """
        ).fetchone()
        concept_count = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
        evidence_count = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

    assert result.concepts_seen >= 1
    assert result.concepts_created >= 1
    assert concept_count == result.concepts_created
    assert evidence_count == result.evidence_created
    assert row is not None
    assert row["concept_id"].startswith("concept:unknown:")
    assert row["status"] == "candidate"
    assert row["canonical_label_ja"] == "エンジンがかからない"
    assert row["canonical_label_en"] == "engine does not start"
    assert row["safe_for_query_expansion"] == 0
    assert row["safe_for_answer_generation"] == 0
    assert row["evidence_type"] == "matched_block_terms"
    assert row["score"] >= 0.25
    assert "P0A80" in row["ja_context"]
    assert "P0A80" in row["en_context"]


def test_build_concepts_is_idempotent_and_preserves_stable_concept_ids(tmp_path):
    db_path = _prepare_db(tmp_path)

    first = build_concepts(db_path=db_path, min_match_score=0.25)
    with sqlite3.connect(db_path) as conn:
        first_ids = [row[0] for row in conn.execute("SELECT concept_id FROM concepts ORDER BY concept_id")]
        first_concept_terms = conn.execute("SELECT COUNT(*) FROM concept_terms").fetchone()[0]
        first_evidence = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

    second = build_concepts(db_path=db_path, min_match_score=0.25)
    with sqlite3.connect(db_path) as conn:
        second_ids = [row[0] for row in conn.execute("SELECT concept_id FROM concepts ORDER BY concept_id")]
        second_concept_terms = conn.execute("SELECT COUNT(*) FROM concept_terms").fetchone()[0]
        second_evidence = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

    assert second.concepts_created == 0
    assert second.concept_terms_created == 0
    assert second.evidence_created == 0
    assert second_ids == first_ids
    assert second_concept_terms == first_concept_terms
    assert second_evidence == first_evidence
    assert first.concepts_seen == second.concepts_seen
