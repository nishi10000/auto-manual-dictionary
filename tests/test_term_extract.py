import sqlite3
from pathlib import Path

from auto_manual_dict.ingest import ingest_directory
from auto_manual_dict.term_extract import extract_terms_from_text, extract_terms_to_db

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_terms_from_japanese_preserves_automotive_terms():
    terms = extract_terms_from_text("ja", "エンジン始動不良。補機バッテリー電圧を確認し、締付トルクを点検する。")
    normalized = {term.normalized_term for term in terms}

    assert "始動不良" in normalized
    assert "補機バッテリー" in normalized
    assert "締付トルク" in normalized


def test_extract_terms_from_english_preserves_domain_phrases():
    terms = extract_terms_from_text("en", "Engine does not start. Check auxiliary battery voltage and tightening torque.")
    normalized = {term.normalized_term for term in terms}

    assert "engine does not start" in normalized
    assert "auxiliary battery" in normalized
    assert "tightening torque" in normalized


def test_extract_terms_to_db_is_idempotent_and_keeps_occurrences(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)

    first = extract_terms_to_db(db_path=db_path)
    second = extract_terms_to_db(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        term_rows = conn.execute("SELECT lang, normalized_term, term_type FROM terms").fetchall()
        terms = {(row[0], row[1]) for row in term_rows}
        term_count = conn.execute("SELECT COUNT(*) FROM terms").fetchone()[0]
        occurrence_count = conn.execute("SELECT COUNT(*) FROM term_occurrences").fetchone()[0]
        duplicate_occurrences = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
              SELECT term_id, block_id, COUNT(*) AS c
              FROM term_occurrences
              GROUP BY term_id, block_id
              HAVING c > 1
            )
            """
        ).fetchone()[0]

    assert first.terms_seen >= 8
    assert second.terms_created == 0
    assert second.occurrences_created == 0
    assert term_count == first.terms_created
    assert occurrence_count == first.occurrences_created
    assert duplicate_occurrences == 0
    assert ("ja", "始動不良") in terms
    assert ("ja", "締付トルク") in terms
    assert ("en", "engine does not start") in terms
    assert ("en", "tightening torque") in terms
