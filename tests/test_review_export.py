import csv
import json
import sqlite3
from pathlib import Path

import pytest

from auto_manual_dict.block_matcher import match_blocks
from auto_manual_dict.concepts import build_concepts
from auto_manual_dict.confidence import update_confidence
from auto_manual_dict.export import export_dictionary, export_review_queue
from auto_manual_dict.ingest import ingest_directory
from auto_manual_dict.review import apply_review_action, import_review_actions
from auto_manual_dict.term_extract import extract_terms_to_db

FIXTURES = Path(__file__).parent / "fixtures"


def _prepare_db(tmp_path):
    db_path = tmp_path / "dict.sqlite3"
    ingest_directory(lang="ja", input_dir=FIXTURES / "ja", db_path=db_path)
    ingest_directory(lang="en", input_dir=FIXTURES / "en", db_path=db_path)
    match_blocks(db_path=db_path, min_score=0.25, top_k_per_block=3)
    extract_terms_to_db(db_path=db_path)
    build_concepts(db_path=db_path, min_match_score=0.25)
    update_confidence(db_path=db_path, review_ready_threshold=0.40)
    return db_path


def _first_review_ready_concept_id(db_path):
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT concept_id FROM concepts WHERE status = 'review_ready' ORDER BY confidence DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    return row[0]


def test_export_review_queue_writes_review_ready_csv_with_context_and_row_version(tmp_path):
    db_path = _prepare_db(tmp_path)
    out_path = tmp_path / "review_ready.csv"

    result = export_review_queue(db_path=db_path, out_path=out_path, fmt="csv")

    rows = list(csv.DictReader(out_path.open(encoding="utf-8")))
    assert result.rows_exported == len(rows)
    assert rows
    row = rows[0]
    expected_columns = {
        "concept_id", "category", "confidence", "confidence_json", "status",
        "ja_terms", "en_terms", "evidence_count", "evidence_ids", "evidence_types",
        "evidence_summary", "sample_ja_context", "sample_en_context", "anchors",
        "source_files", "recommended_action", "action", "reviewer", "reason", "reason_code",
        "review_note", "row_version", "export_batch_id",
    }
    assert expected_columns <= set(row)
    assert row["status"] == "review_ready"
    assert row["concept_id"].startswith("concept:")
    assert row["ja_terms"]
    assert row["en_terms"]
    assert int(row["evidence_count"]) > 0
    assert int(row["row_version"]) == 0
    assert row["export_batch_id"]
    assert row["action"] == ""
    assert row["reviewer"] == ""
    assert row["reason"] == ""
    assert row["reason_code"] == ""
    assert row["sample_ja_context"]
    assert row["sample_en_context"]


def test_review_actions_approve_block_and_defer_change_status_with_audit_history(tmp_path):
    db_path = _prepare_db(tmp_path)
    concept_id = _first_review_ready_concept_id(db_path)

    approved = apply_review_action(
        db_path=db_path,
        concept_id=concept_id,
        action="approve",
        reviewer="nishihara",
        reason="verified bilingual evidence",
    )
    blocked = apply_review_action(
        db_path=db_path,
        concept_id=concept_id,
        action="block",
        reviewer="nishihara",
        reason_code="wrong_context",
        reason="unsafe mismatch",
    )
    deferred = apply_review_action(
        db_path=db_path,
        concept_id=concept_id,
        action="defer",
        reviewer="nishihara",
        reason="needs more evidence",
    )

    with sqlite3.connect(db_path) as conn:
        status = conn.execute("SELECT status FROM concepts WHERE concept_id = ?", (concept_id,)).fetchone()[0]
        actions = conn.execute(
            "SELECT action, previous_status, new_status, reviewer, reason_code FROM review_actions WHERE target_id = ? ORDER BY id",
            (concept_id,),
        ).fetchall()

    assert approved.new_status == "confirmed"
    assert blocked.new_status == "blocked"
    assert deferred.new_status == "candidate"
    assert status == "candidate"
    assert [row[0] for row in actions] == ["approve", "block", "defer"]
    assert actions[0][1] == "review_ready"
    assert actions[0][2] == "confirmed"
    assert actions[1][4] == "wrong_context"


def test_import_review_actions_rejects_stale_row_version(tmp_path):
    db_path = _prepare_db(tmp_path)
    concept_id = _first_review_ready_concept_id(db_path)
    stale_csv = tmp_path / "stale.csv"
    with stale_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["concept_id", "row_version", "action", "reviewer", "reason"])
        writer.writeheader()
        writer.writerow({
            "concept_id": concept_id,
            "row_version": "999",
            "action": "approve",
            "reviewer": "nishihara",
            "reason": "stale approval",
        })

    with pytest.raises(ValueError, match="row_version mismatch"):
        import_review_actions(db_path=db_path, input_path=stale_csv)


def test_import_review_actions_dry_run_validates_without_mutating_db_and_writes_report(tmp_path):
    db_path = _prepare_db(tmp_path)
    concept_id = _first_review_ready_concept_id(db_path)
    review_csv = tmp_path / "review.csv"
    report_csv = tmp_path / "report.csv"
    with review_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["concept_id", "row_version", "action", "reviewer", "reason"])
        writer.writeheader()
        writer.writerow({
            "concept_id": concept_id,
            "row_version": "0",
            "action": "approve",
            "reviewer": "nishihara",
            "reason": "dry run only",
        })

    result = import_review_actions(db_path=db_path, input_path=review_csv, dry_run=True, report_path=report_csv)

    with sqlite3.connect(db_path) as conn:
        status = conn.execute("SELECT status FROM concepts WHERE concept_id = ?", (concept_id,)).fetchone()[0]
        action_count = conn.execute("SELECT COUNT(*) FROM review_actions WHERE target_id = ?", (concept_id,)).fetchone()[0]
    report_rows = list(csv.DictReader(report_csv.open(encoding="utf-8")))

    assert result.rows_seen == 1
    assert result.actions_valid == 1
    assert result.actions_applied == 0
    assert status == "review_ready"
    assert action_count == 0
    assert report_rows[0]["import_status"] == "valid"
    assert report_rows[0]["new_status"] == "confirmed"
    assert report_rows[0]["error_message"] == ""


def test_import_review_actions_validates_all_rows_before_applying_any_action(tmp_path):
    db_path = _prepare_db(tmp_path)
    concept_id = _first_review_ready_concept_id(db_path)
    mixed_csv = tmp_path / "mixed.csv"
    with mixed_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["concept_id", "row_version", "action", "reviewer", "reason"])
        writer.writeheader()
        writer.writerow({
            "concept_id": concept_id,
            "row_version": "0",
            "action": "approve",
            "reviewer": "nishihara",
            "reason": "would be valid alone",
        })
        writer.writerow({
            "concept_id": concept_id,
            "row_version": "999",
            "action": "approve",
            "reviewer": "nishihara",
            "reason": "stale approval",
        })

    with pytest.raises(ValueError, match="row_version mismatch"):
        import_review_actions(db_path=db_path, input_path=mixed_csv)

    with sqlite3.connect(db_path) as conn:
        status = conn.execute("SELECT status FROM concepts WHERE concept_id = ?", (concept_id,)).fetchone()[0]
        action_count = conn.execute("SELECT COUNT(*) FROM review_actions WHERE target_id = ?", (concept_id,)).fetchone()[0]

    assert status == "review_ready"
    assert action_count == 0


def test_import_review_actions_write_back_records_applied_status_and_new_row_version(tmp_path):
    db_path = _prepare_db(tmp_path)
    concept_id = _first_review_ready_concept_id(db_path)
    review_csv = tmp_path / "review.csv"
    write_back_csv = tmp_path / "write_back.csv"
    with review_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["concept_id", "row_version", "action", "reviewer", "reason"])
        writer.writeheader()
        writer.writerow({
            "concept_id": concept_id,
            "row_version": "0",
            "action": "approve",
            "reviewer": "nishihara",
            "reason": "verified",
        })

    result = import_review_actions(db_path=db_path, input_path=review_csv, write_back_path=write_back_csv)

    rows = list(csv.DictReader(write_back_csv.open(encoding="utf-8")))
    assert result.actions_applied == 1
    assert rows[0]["import_status"] == "applied"
    assert rows[0]["new_status"] == "confirmed"
    assert rows[0]["new_row_version"] == "1"
    assert rows[0]["error_message"] == ""


def test_confirmed_only_dictionary_exports_exclude_unreviewed_concepts(tmp_path):
    db_path = _prepare_db(tmp_path)
    concept_id = _first_review_ready_concept_id(db_path)
    out_path = tmp_path / "dictionary.jsonl"

    before = export_dictionary(db_path=db_path, out_path=out_path, fmt="jsonl")
    assert before.rows_exported == 0
    assert out_path.read_text(encoding="utf-8") == ""

    apply_review_action(
        db_path=db_path,
        concept_id=concept_id,
        action="approve",
        reviewer="nishihara",
        reason="verified",
    )
    after = export_dictionary(db_path=db_path, out_path=out_path, fmt="jsonl")
    lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]

    assert after.rows_exported == 1
    assert lines[0]["concept_id"] == concept_id
    assert lines[0]["status"] == "confirmed"
    assert lines[0]["ja_terms"]
    assert lines[0]["en_terms"]
