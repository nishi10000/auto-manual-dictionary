import sqlite3

from auto_manual_dict.db import init_db


def test_init_db_creates_minimum_sprint_tables(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert {"documents", "document_blocks", "anchors", "ingestion_runs"}.issubset(tables)
