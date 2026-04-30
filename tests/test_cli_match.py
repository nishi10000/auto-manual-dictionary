import sqlite3
from pathlib import Path

from auto_manual_dict.cli import main
from auto_manual_dict.ingest import ingest_directory
from auto_manual_dict.term_extract import extract_terms_to_db

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_match_blocks_and_pages_persist_candidates(tmp_path, capsys):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)

    assert main(["match-blocks", "--db", str(db_path)]) == 0
    block_output = capsys.readouterr().out
    assert "block_candidates_written=" in block_output

    assert main(["match-pages", "--db", str(db_path)]) == 0
    page_output = capsys.readouterr().out
    assert "page_candidates_written=" in page_output

    extract_terms_to_db(db_path=db_path)
    assert main(["build-concepts", "--db", str(db_path)]) == 0
    concept_output = capsys.readouterr().out
    assert "concepts_seen=" in concept_output
    assert "evidence_created=" in concept_output

    assert main(["update-confidence", "--db", str(db_path)]) == 0
    confidence_output = capsys.readouterr().out
    assert "concepts_updated=" in confidence_output
    assert "review_ready=" in confidence_output

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM block_match_candidates").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM page_match_candidates").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM concept_terms").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM concepts WHERE confidence_version = 'confidence_mvp_0.1'").fetchone()[0] > 0
