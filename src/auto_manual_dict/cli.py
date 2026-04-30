from __future__ import annotations

import argparse
from pathlib import Path

from .block_matcher import match_blocks
from .concepts import build_concepts
from .confidence import update_confidence
from .export import export_answer_generation, export_dictionary, export_query_expansion, export_review_queue
from .ingest import ingest_directory
from .page_matcher import match_pages
from .review import apply_review_action, import_review_actions
from .term_extract import extract_terms_to_db


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
    "defer",
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
        if name in {"match-blocks", "match-pages", "build-concepts"}:
            cmd.add_argument("--min-score", type=float)
        if name == "update-confidence":
            cmd.add_argument("--review-ready-threshold", type=float)
        if name in {"match-blocks", "match-pages"}:
            cmd.add_argument("--top-k", type=int)

    export_review = subparsers.add_parser("export-review")
    export_review.add_argument("--db", type=Path, required=True)
    export_review.add_argument("--out", type=Path, required=True)
    export_review.add_argument("--format", choices=["csv", "jsonl"], default="csv")
    export_review.add_argument("--status", default="review_ready")

    import_review = subparsers.add_parser("import-review")
    import_review.add_argument("--db", type=Path, required=True)
    import_review.add_argument("--input", type=Path, required=True)

    approve = subparsers.add_parser("approve")
    approve.add_argument("--db", type=Path, required=True)
    approve.add_argument("--concept-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reason", required=True)
    approve.add_argument("--row-version", type=int)

    block = subparsers.add_parser("block")
    block.add_argument("--db", type=Path, required=True)
    block.add_argument("--concept-id", required=True)
    block.add_argument("--reviewer", required=True)
    block.add_argument("--reason-code", required=True)
    block.add_argument("--reason")
    block.add_argument("--row-version", type=int)

    defer = subparsers.add_parser("defer")
    defer.add_argument("--db", type=Path, required=True)
    defer.add_argument("--concept-id", required=True)
    defer.add_argument("--reviewer", required=True)
    defer.add_argument("--reason", required=True)
    defer.add_argument("--row-version", type=int)

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
    if args.command == "extract-terms":
        result = extract_terms_to_db(db_path=args.db)
        print(
            " ".join(
                [
                    f"terms_seen={result.terms_seen}",
                    f"terms_created={result.terms_created}",
                    f"occurrences_created={result.occurrences_created}",
                ]
            )
        )
        return 0
    if args.command == "build-concepts":
        result = build_concepts(
            db_path=args.db,
            min_match_score=0.25 if args.min_score is None else args.min_score,
        )
        print(
            " ".join(
                [
                    f"concepts_seen={result.concepts_seen}",
                    f"concepts_created={result.concepts_created}",
                    f"concept_terms_created={result.concept_terms_created}",
                    f"evidence_created={result.evidence_created}",
                ]
            )
        )
        return 0
    if args.command == "update-confidence":
        result = update_confidence(
            db_path=args.db,
            review_ready_threshold=0.85 if args.review_ready_threshold is None else args.review_ready_threshold,
        )
        print(
            " ".join(
                [
                    f"concepts_seen={result.concepts_seen}",
                    f"concepts_updated={result.concepts_updated}",
                    f"review_ready={result.review_ready}",
                ]
            )
        )
        return 0
    if args.command == "export-review":
        result = export_review_queue(db_path=args.db, out_path=args.out, fmt=args.format, status=args.status)
        print(f"rows_exported={result.rows_exported} out={result.out_path}")
        return 0
    if args.command == "import-review":
        result = import_review_actions(db_path=args.db, input_path=args.input)
        print(f"rows_seen={result.rows_seen} actions_applied={result.actions_applied}")
        return 0
    if args.command in {"approve", "block", "defer"}:
        result = apply_review_action(
            db_path=args.db,
            concept_id=args.concept_id,
            action=args.command,
            reviewer=args.reviewer,
            reason=getattr(args, "reason", None),
            reason_code=getattr(args, "reason_code", None),
            row_version=getattr(args, "row_version", None),
        )
        print(
            " ".join(
                [
                    f"concept_id={result.concept_id}",
                    f"action={result.action}",
                    f"previous_status={result.previous_status}",
                    f"new_status={result.new_status}",
                    f"row_version={result.row_version}",
                ]
            )
        )
        return 0
    if args.command == "export-dictionary":
        result = export_dictionary(db_path=args.db, out_path=args.out, fmt=args.format)
        print(f"rows_exported={result.rows_exported} out={result.out_path}")
        return 0
    if args.command == "export-query-expansion":
        result = export_query_expansion(db_path=args.db, out_path=args.out)
        print(f"rows_exported={result.rows_exported} out={result.out_path}")
        return 0
    if args.command == "export-rag-safe":
        result = export_answer_generation(db_path=args.db, out_path=args.out)
        print(f"rows_exported={result.rows_exported} out={result.out_path}")
        return 0
    parser.exit(status=2, message=f"Command '{args.command}' is not implemented yet. See docs/plans/implementation-plan.md.\n")
    return 2
