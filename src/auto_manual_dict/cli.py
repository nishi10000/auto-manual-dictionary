from __future__ import annotations

import argparse
from pathlib import Path

from .block_matcher import match_blocks
from .ingest import ingest_directory
from .page_matcher import match_pages


COMMANDS = [
    "ingest",
    "match-blocks",
    "match-pages",
    "extract-terms",
    "build-concepts",
    "update-confidence",
    "export-review",
    "import-review",
    "approve",
    "block",
    "export-dictionary",
    "export-query-expansion",
    "export-rag-safe",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto-manual-dict",
        description="Build and review a local Japanese/English automotive manual terminology dictionary.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest local HTML manual files")
    ingest.add_argument("--lang", choices=["ja", "en"], required=True)
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--db", type=Path, required=True)

    for name in ["match-blocks", "match-pages", "extract-terms", "build-concepts", "update-confidence"]:
        cmd = subparsers.add_parser(name)
        cmd.add_argument("--db", type=Path, required=True)
        if name in {"match-blocks", "match-pages"}:
            cmd.add_argument("--min-score", type=float)
            cmd.add_argument("--top-k", type=int)

    export_review = subparsers.add_parser("export-review")
    export_review.add_argument("--db", type=Path, required=True)
    export_review.add_argument("--out", type=Path, required=True)

    import_review = subparsers.add_parser("import-review")
    import_review.add_argument("--db", type=Path, required=True)
    import_review.add_argument("--input", type=Path, required=True)

    approve = subparsers.add_parser("approve")
    approve.add_argument("--db", type=Path, required=True)
    approve.add_argument("--concept-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reason", required=True)

    block = subparsers.add_parser("block")
    block.add_argument("--db", type=Path, required=True)
    block.add_argument("--concept-id", required=True)
    block.add_argument("--reviewer", required=True)
    block.add_argument("--reason-code", required=True)
    block.add_argument("--reason")

    for name in ["export-dictionary", "export-query-expansion", "export-rag-safe"]:
        cmd = subparsers.add_parser(name)
        cmd.add_argument("--db", type=Path, required=True)
        cmd.add_argument("--out", type=Path, required=True)
        if name == "export-dictionary":
            cmd.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest":
        result = ingest_directory(lang=args.lang, input_dir=args.input, db_path=args.db)
        print(
            " ".join(
                [
                    f"documents_seen={result.documents_seen}",
                    f"documents_inserted={result.documents_inserted}",
                    f"documents_updated={result.documents_updated}",
                    f"blocks_written={result.blocks_written}",
                    f"anchors_written={result.anchors_written}",
                    f"errors={result.errors}",
                ]
            )
        )
        return 0 if result.errors == 0 else 1
    if args.command == "match-blocks":
        result = match_blocks(
            db_path=args.db,
            min_score=0.20 if args.min_score is None else args.min_score,
            top_k_per_block=5 if args.top_k is None else args.top_k,
        )
        print(f"block_candidates_written={result.candidates_written}")
        return 0
    if args.command == "match-pages":
        result = match_pages(
            db_path=args.db,
            min_score=0.25 if args.min_score is None else args.min_score,
            top_k_per_document=5 if args.top_k is None else args.top_k,
        )
        print(f"page_candidates_written={result.candidates_written}")
        return 0
    parser.exit(status=2, message=f"Command '{args.command}' is not implemented yet. See docs/plans/implementation-plan.md.\n")
    return 2
