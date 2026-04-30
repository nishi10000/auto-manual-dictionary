import sqlite3
from pathlib import Path

from auto_manual_dict.ingest import ingest_directory

FIXTURES = Path(__file__).parent / "fixtures"


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def html_count(lang: str) -> int:
    return len(list((FIXTURES / lang).glob("*.html")))


def test_ingest_directory_stores_documents_blocks_and_anchors_idempotently(tmp_path):
    db_path = tmp_path / "dict.sqlite3"

    first = ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    second = ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)

    expected_docs = html_count("ja")
    assert first.documents_seen == expected_docs
    assert second.documents_seen == expected_docs

    with sqlite3.connect(db_path) as conn:
        assert count(conn, "documents") == expected_docs
        assert count(conn, "document_blocks") >= 15
        assert count(conn, "anchors") >= 8
        dtcs = {row[0] for row in conn.execute("SELECT normalized_value FROM anchors WHERE anchor_type='dtc'")}
        assert {"P0A80", "B1801"}.issubset(dtcs)
        safety_blocks = {row[0] for row in conn.execute("SELECT DISTINCT block_type FROM document_blocks WHERE block_type IN ('warning','caution','note','prohibition')")}
        assert {"warning", "caution", "note", "prohibition"}.issubset(safety_blocks)


def test_reingest_unchanged_files_keeps_block_ids_stable_and_does_not_update(tmp_path):
    db_path = tmp_path / "dict.sqlite3"

    first = ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        before = conn.execute(
            """
            SELECT documents.path, document_blocks.block_index, document_blocks.id
            FROM document_blocks
            JOIN documents ON documents.id = document_blocks.document_id
            ORDER BY documents.path, document_blocks.block_index
            """
        ).fetchall()

    second = ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        after = conn.execute(
            """
            SELECT documents.path, document_blocks.block_index, document_blocks.id
            FROM document_blocks
            JOIN documents ON documents.id = document_blocks.document_id
            ORDER BY documents.path, document_blocks.block_index
            """
        ).fetchall()

    assert first.documents_inserted == html_count("ja")
    assert second.documents_inserted == 0
    assert second.documents_updated == 0
    assert before == after


def test_ingest_stores_raw_html_locally_for_reproducibility(tmp_path):
    db_path = tmp_path / "dict.sqlite3"

    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        source_html = conn.execute(
            "SELECT source_html FROM documents WHERE path = ?",
            ("engine_no_start.html",),
        ).fetchone()[0]

    assert "<title>エンジン始動不良</title>" in source_html
    assert "DTC P0A80" in source_html


def test_reingest_backfills_legacy_missing_source_html_without_changing_block_ids(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        before = conn.execute(
            "SELECT id FROM document_blocks ORDER BY document_id, block_index"
        ).fetchall()
        conn.execute("UPDATE documents SET source_html = NULL WHERE path = ?", ("engine_no_start.html",))
        conn.commit()

    result = ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        after = conn.execute(
            "SELECT id FROM document_blocks ORDER BY document_id, block_index"
        ).fetchall()
        source_html = conn.execute(
            "SELECT source_html FROM documents WHERE path = ?",
            ("engine_no_start.html",),
        ).fetchone()[0]

    assert result.documents_updated == 1
    assert result.errors == 0
    assert before == after
    assert source_html is not None
    assert "DTC P0A80" in source_html


def test_reingest_changed_document_removes_stale_match_candidates_before_replacing_blocks(tmp_path):
    import shutil

    fixture_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixture_copy)
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=fixture_copy / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=fixture_copy / "en", db_path=db_path)

    from auto_manual_dict.block_matcher import match_blocks
    from auto_manual_dict.page_matcher import match_pages

    match_blocks(db_path=db_path, min_score=0.20)
    match_pages(db_path=db_path, min_score=0.25)
    changed = fixture_copy / "ja" / "engine_no_start.html"
    changed.write_text(changed.read_text(encoding="utf-8").replace("P0A80", "P0A81"), encoding="utf-8")

    result = ingest_directory(lang="ja", input_dir=fixture_copy / "ja", db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        dangling_block_matches = conn.execute(
            """
            SELECT COUNT(*)
            FROM block_match_candidates bmc
            LEFT JOIN document_blocks jb ON jb.id = bmc.ja_block_id
            LEFT JOIN document_blocks eb ON eb.id = bmc.en_block_id
            WHERE jb.id IS NULL OR eb.id IS NULL
            """
        ).fetchone()[0]
        stale_page_matches = conn.execute(
            """
            SELECT COUNT(*)
            FROM page_match_candidates pmc
            JOIN documents dja ON dja.id = pmc.ja_document_id
            WHERE dja.path = 'engine_no_start.html'
            """
        ).fetchone()[0]

    assert result.errors == 0
    assert result.documents_updated == 1
    assert dangling_block_matches == 0
    assert stale_page_matches == 0


def test_ingest_both_languages_keeps_language_separate(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        langs = dict(conn.execute("SELECT lang, COUNT(*) FROM documents GROUP BY lang"))
    assert langs == {"en": html_count("en"), "ja": html_count("ja")}
