import csv
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "auto_manual_dict", *map(str, args)],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


def test_end_to_end_cli_flow_on_tiny_asymmetric_no_start_corpus(tmp_path):
    ja_input = tmp_path / "ja"
    en_input = tmp_path / "en"
    ja_input.mkdir()
    en_input.mkdir()

    fixture_paths = [
        FIXTURES / "ja" / "no_start.html",
        FIXTURES / "en" / "engine_no_start_a.html",
        FIXTURES / "en" / "engine_no_start_b.html",
    ]
    for path in fixture_paths:
        assert path.exists(), f"missing E2E fixture: {path}"

    (ja_input / "no_start.html").write_text(fixture_paths[0].read_text(encoding="utf-8"), encoding="utf-8")
    (en_input / "engine_no_start_a.html").write_text(fixture_paths[1].read_text(encoding="utf-8"), encoding="utf-8")
    (en_input / "engine_no_start_b.html").write_text(fixture_paths[2].read_text(encoding="utf-8"), encoding="utf-8")

    db_path = tmp_path / "dict.sqlite3"
    review_csv = tmp_path / "review.csv"
    dictionary_jsonl = tmp_path / "dictionary.jsonl"

    commands = [
        ("ingest", "--lang", "ja", "--input", ja_input, "--db", db_path),
        ("ingest", "--lang", "en", "--input", en_input, "--db", db_path),
        ("match-pages", "--db", db_path),
        ("match-blocks", "--db", db_path),
        ("extract-terms", "--db", db_path),
        ("build-concepts", "--db", db_path),
        ("update-confidence", "--db", db_path, "--review-ready-threshold", "0.40"),
        ("export-review", "--db", db_path, "--out", review_csv),
    ]
    outputs = [_run_cli(*command).stdout for command in commands]

    assert all(output.strip() for output in outputs)
    rows = list(csv.DictReader(review_csv.open(encoding="utf-8")))
    assert rows
    joined_rows = json.dumps(rows, ensure_ascii=False).lower()
    assert "始動不良" in joined_rows
    assert "engine" in joined_rows and ("does not start" in joined_rows or "no start" in joined_rows)

    first = rows[0]
    approve = _run_cli(
        "approve",
        "--db",
        db_path,
        "--concept-id",
        first["concept_id"],
        "--reviewer",
        "e2e-reviewer",
        "--reason",
        "fixture evidence verified",
        "--row-version",
        first["row_version"],
    )
    assert "new_status=confirmed" in approve.stdout

    export_dict = _run_cli("export-dictionary", "--db", db_path, "--out", dictionary_jsonl)
    assert "rows_exported=1" in export_dict.stdout
    exported = [json.loads(line) for line in dictionary_jsonl.read_text(encoding="utf-8").splitlines()]
    assert exported[0]["status"] == "confirmed"

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE lang = 'ja'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE lang = 'en'").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM page_match_candidates").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM block_match_candidates").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM review_actions WHERE reviewer = 'e2e-reviewer'").fetchone()[0] == 1
