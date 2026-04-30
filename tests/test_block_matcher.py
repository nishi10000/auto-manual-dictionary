import json
import sqlite3
from pathlib import Path

from auto_manual_dict.block_matcher import match_blocks, score_block_pair
from auto_manual_dict.ingest import ingest_directory

FIXTURES = Path(__file__).parent / "fixtures"


def _prepare_db(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)
    return db_path


def _block(conn, lang, path, contains):
    row = conn.execute(
        """
        SELECT document_blocks.*
        FROM document_blocks
        JOIN documents ON documents.id = document_blocks.document_id
        WHERE documents.lang = ? AND documents.path = ? AND document_blocks.text LIKE ?
        ORDER BY document_blocks.block_index
        LIMIT 1
        """,
        (lang, path, f"%{contains}%"),
    ).fetchone()
    assert row is not None
    return row


def test_score_block_pair_rewards_shared_strong_anchors_more_than_unrelated(tmp_path):
    db_path = _prepare_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ja = _block(conn, "ja", "engine_no_start.html", "P0A80")
        en_related = _block(conn, "en", "engine_no_start.html", "P0A80")
        en_unrelated = _block(conn, "en", "unmatched_en.html", "English manual")

        related = score_block_pair(conn, ja["id"], en_related["id"])
        unrelated = score_block_pair(conn, ja["id"], en_unrelated["id"])

    assert related.score >= 0.35
    assert related.score > unrelated.score
    assert related.evidence["shared_anchors"]["dtc"] == ["P0A80"]


def test_score_block_pair_accepts_default_sqlite_connection_rows(tmp_path):
    db_path = _prepare_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        ja = _block(conn, "ja", "engine_no_start.html", "P0A80")
        en = _block(conn, "en", "engine_no_start.html", "P0A80")
        score = score_block_pair(conn, ja[0], en[0])
    assert score.score >= 0.35


def test_match_blocks_persists_multiple_candidates_for_one_japanese_page(tmp_path):
    db_path = _prepare_db(tmp_path)

    result = match_blocks(db_path=db_path, min_score=0.20, top_k_per_block=3)
    second = match_blocks(db_path=db_path, min_score=0.20, top_k_per_block=3)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT dja.path AS ja_path, den.path AS en_path, bmc.score, bmc.evidence_json
            FROM block_match_candidates bmc
            JOIN document_blocks jb ON jb.id = bmc.ja_block_id
            JOIN documents dja ON dja.id = jb.document_id
            JOIN document_blocks eb ON eb.id = bmc.en_block_id
            JOIN documents den ON den.id = eb.document_id
            WHERE dja.path = 'engine_no_start.html'
            ORDER BY bmc.score DESC
            """
        ).fetchall()
        count_after_second = conn.execute("SELECT COUNT(*) FROM block_match_candidates").fetchone()[0]

    assert result.candidates_written >= 2
    assert second.candidates_written == result.candidates_written
    assert count_after_second == result.candidates_written
    assert any(row[1] == "engine_no_start.html" and row[2] >= 0.35 for row in rows)
    assert len({(row[0], row[1]) for row in rows}) >= 1
    assert any("shared_anchors" in json.loads(row[3]) for row in rows)


def test_unmatched_pages_stay_below_threshold(tmp_path):
    db_path = _prepare_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ja = _block(conn, "ja", "unmatched_jp.html", "日本語版")
        en = _block(conn, "en", "unmatched_en.html", "English manual")
        score = score_block_pair(conn, ja["id"], en["id"])
    assert score.score < 0.20
