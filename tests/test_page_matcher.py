import json
import sqlite3
from pathlib import Path

from auto_manual_dict.ingest import ingest_directory
from auto_manual_dict.page_matcher import match_pages, score_page_pair

FIXTURES = Path(__file__).parent / "fixtures"


def _prepare_db(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)
    return db_path


def _doc_id(conn, lang, path):
    row = conn.execute("SELECT id FROM documents WHERE lang = ? AND path = ?", (lang, path)).fetchone()
    assert row is not None
    return row[0]


def test_score_page_pair_uses_shared_document_anchors_as_supplemental_signal(tmp_path):
    db_path = _prepare_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        related = score_page_pair(conn, _doc_id(conn, "ja", "engine_no_start.html"), _doc_id(conn, "en", "engine_no_start.html"))
        unrelated = score_page_pair(conn, _doc_id(conn, "ja", "engine_no_start.html"), _doc_id(conn, "en", "unmatched_en.html"))
    assert related.score >= 0.50
    assert related.score > unrelated.score
    assert "P0A80" in related.evidence["shared_anchors"]["dtc"]


def test_match_pages_persists_idempotent_candidates_without_forcing_1_to_1(tmp_path):
    db_path = _prepare_db(tmp_path)

    result = match_pages(db_path=db_path, min_score=0.25, top_k_per_document=3)
    second = match_pages(db_path=db_path, min_score=0.25, top_k_per_document=3)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT dja.path, den.path, pmc.score, pmc.match_type, pmc.evidence_json
            FROM page_match_candidates pmc
            JOIN documents dja ON dja.id = pmc.ja_document_id
            JOIN documents den ON den.id = pmc.en_document_id
            ORDER BY pmc.score DESC
            """
        ).fetchall()
        count_after_second = conn.execute("SELECT COUNT(*) FROM page_match_candidates").fetchone()[0]

    assert result.candidates_written > 0
    assert second.candidates_written == result.candidates_written
    assert count_after_second == result.candidates_written
    assert any(row[0] == "engine_no_start.html" and row[1] == "engine_no_start.html" for row in rows)
    assert all(row[3] == "supplemental_anchor_score" for row in rows)
    assert all("shared_anchors" in json.loads(row[4]) for row in rows)
