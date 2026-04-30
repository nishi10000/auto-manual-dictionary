import sqlite3
from pathlib import Path

from auto_manual_dict.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def html_count(lang: str) -> int:
    return len(list((FIXTURES / lang).glob("*.html")))


def test_cli_ingest_runs_and_returns_success(tmp_path, capsys):
    db_path = tmp_path / "dict.sqlite3"

    rc = main(["ingest", "--lang", "ja", "--input", str(FIXTURES / "ja"), "--db", str(db_path)])

    assert rc == 0
    output = capsys.readouterr().out
    expected_docs = html_count("ja")
    assert f"documents_seen={expected_docs}" in output
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == expected_docs
