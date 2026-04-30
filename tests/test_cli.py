from auto_manual_dict.cli import build_parser


def test_parser_has_ingest_command():
    parser = build_parser()
    args = parser.parse_args([
        "ingest",
        "--lang",
        "ja",
        "--input",
        "manuals/ja",
        "--db",
        "work/dict.sqlite3",
    ])
    assert args.command == "ingest"
    assert args.lang == "ja"
    assert str(args.input) == "manuals/ja"


def test_parser_has_review_commands():
    parser = build_parser()
    args = parser.parse_args([
        "export-review",
        "--db",
        "work/dict.sqlite3",
        "--out",
        "review/review_ready.csv",
    ])
    assert args.command == "export-review"


def test_parser_has_import_review_operational_safety_options():
    parser = build_parser()
    args = parser.parse_args([
        "import-review",
        "--db",
        "work/dict.sqlite3",
        "--input",
        "review/review_ready.csv",
        "--dry-run",
        "--report",
        "review/import_report.csv",
        "--write-back",
        "review/review_imported.csv",
    ])
    assert args.command == "import-review"
    assert args.dry_run is True
    assert str(args.report) == "review/import_report.csv"
    assert str(args.write_back) == "review/review_imported.csv"


def test_parser_has_safe_export_commands():
    parser = build_parser()
    args = parser.parse_args([
        "export-query-expansion",
        "--db",
        "work/dict.sqlite3",
        "--out",
        "dist/query_expansion.jsonl",
    ])
    assert args.command == "export-query-expansion"
