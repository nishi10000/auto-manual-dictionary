import sqlite3
from pathlib import Path

from auto_manual_dict.cli import main
from auto_manual_dict.ingest import ingest_directory

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_extract_terms_persists_terms(tmp_path, capsys):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)

    assert main(["extract-terms", "--db", str(db_path)]) == 0
    output = capsys.readouterr().out
    assert "terms_seen=" in output
    assert "terms_created=" in output

    with sqlite3.connect(db_path) as conn:
        terms = {row[0] for row in conn.execute("SELECT normalized_term FROM terms")}

    assert "補機バッテリー" in terms
    assert "auxiliary battery" in terms
