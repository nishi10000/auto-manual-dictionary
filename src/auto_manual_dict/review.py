from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .db import connect, init_db


@dataclass(frozen=True)
class ReviewActionResult:
    concept_id: str
    action: str
    previous_status: str
    new_status: str
    row_version: int


@dataclass(frozen=True)
class ImportReviewResult:
    actions_applied: int
    rows_seen: int
    actions_valid: int = 0
    actions_skipped: int = 0
    report_path: Path | None = None
    write_back_path: Path | None = None


_ACTION_TO_STATUS = {
    "approve": "confirmed",
    "block": "blocked",
    "defer": "candidate",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_version(conn: sqlite3.Connection, concept_public_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM review_actions WHERE target_type = 'concept' AND target_id = ?",
            (concept_public_id,),
        ).fetchone()[0]
    )


def _evidence_ids_for_concept(conn: sqlite3.Connection, concept_pk: int) -> list[int]:
    return [
        int(row[0])
        for row in conn.execute("SELECT id FROM evidence WHERE concept_id = ? ORDER BY id", (concept_pk,)).fetchall()
    ]


def _validate_action(action: str, reviewer: str | None, reason_code: str | None, reason: str | None) -> None:
    if action not in _ACTION_TO_STATUS:
        raise ValueError(f"unsupported review action: {action}")
    if not reviewer:
        raise ValueError("reviewer is required")
    if action == "approve" and not reason:
        raise ValueError("approve requires reason")
    if action == "block" and not reason_code:
        raise ValueError("block requires reason_code")
    if action == "defer" and not reason:
        raise ValueError("defer requires reason")


def _concept_for_review(conn: sqlite3.Connection, concept_id: str) -> sqlite3.Row:
    concept = conn.execute(
        "SELECT id, concept_id, status FROM concepts WHERE concept_id = ?",
        (concept_id,),
    ).fetchone()
    if concept is None:
        raise ValueError(f"concept not found: {concept_id}")
    return concept


def _apply_review_action_conn(
    conn: sqlite3.Connection,
    *,
    concept_id: str,
    action: str,
    reviewer: str,
    reason: str | None = None,
    reason_code: str | None = None,
    row_version: int | None = None,
) -> ReviewActionResult:
    action = action.strip().lower()
    _validate_action(action, reviewer, reason_code, reason)
    concept = _concept_for_review(conn, concept_id)
    current_version = _row_version(conn, concept_id)
    if row_version is not None and int(row_version) != current_version:
        raise ValueError(f"row_version mismatch for {concept_id}: expected {current_version}, got {row_version}")
    previous_status = concept["status"]
    new_status = _ACTION_TO_STATUS[action]
    now = _now()
    evidence_ids = _evidence_ids_for_concept(conn, int(concept["id"]))
    conn.execute(
        """
        UPDATE concepts
        SET status = ?, updated_at = ?
        WHERE concept_id = ?
        """,
        (new_status, now, concept_id),
    )
    conn.execute(
        """
        INSERT INTO review_actions(
          target_type, target_id, action, previous_status, new_status,
          reviewer, reason_code, reason, evidence_ids_json, row_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "concept",
            concept_id,
            action,
            previous_status,
            new_status,
            reviewer,
            reason_code,
            reason,
            json.dumps(evidence_ids, ensure_ascii=False),
            current_version,
            now,
        ),
    )
    new_version = current_version + 1
    return ReviewActionResult(
        concept_id=concept_id,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        row_version=new_version,
    )


def apply_review_action(
    db_path: str | Path,
    concept_id: str,
    action: str,
    reviewer: str,
    reason: str | None = None,
    reason_code: str | None = None,
    row_version: int | None = None,
) -> ReviewActionResult:
    init_db(db_path)
    with connect(db_path) as conn:
        return _apply_review_action_conn(
            conn,
            concept_id=concept_id,
            action=action,
            reviewer=reviewer,
            reason=reason,
            reason_code=reason_code,
            row_version=row_version,
        )


@dataclass(frozen=True)
class _ValidatedAction:
    row_index: int
    row: dict[str, str]
    concept_id: str
    action: str
    reviewer: str
    reason: str | None
    reason_code: str | None
    row_version: int | None
    previous_status: str
    new_status: str
    new_row_version: int


def _iter_action_rows(input_path: Path) -> Iterable[dict[str, str]]:
    if input_path.suffix.lower() == ".jsonl":
        with input_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return
    with input_path.open(encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def _action_from_row(row: dict[str, str]) -> str:
    if "action" in row:
        return (row.get("action") or "").strip().lower()
    return (row.get("recommended_action") or "").strip().lower()


def _optional_text(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return None


def _report_fieldnames(rows: list[dict[str, str]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fields:
                fields.append(key)
    for key in ["import_status", "new_status", "new_row_version", "error_message"]:
        if key not in fields:
            fields.append(key)
    return fields


def _write_review_report(path: str | Path, rows: list[dict[str, str]]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_report_fieldnames(rows))
        writer.writeheader()
        writer.writerows(rows)
    return out


def _validate_import_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, str]],
) -> tuple[list[_ValidatedAction], list[dict[str, str]], int]:
    validated: list[_ValidatedAction] = []
    report_rows: list[dict[str, str]] = []
    skipped = 0
    planned_versions: dict[str, int] = {}
    first_error: ValueError | None = None

    for index, row in enumerate(rows, start=1):
        report_row = dict(row)
        action = _action_from_row(row)
        if action in {"", "inspect", "split"}:
            skipped += 1
            report_row.update({"import_status": "skipped", "new_status": "", "new_row_version": "", "error_message": ""})
            report_rows.append(report_row)
            continue

        try:
            concept_id = (row.get("concept_id") or "").strip()
            reviewer = (row.get("reviewer") or "").strip()
            reason = _optional_text(row, "reason", "review_note")
            reason_code = _optional_text(row, "reason_code")
            _validate_action(action, reviewer, reason_code, reason)
            concept = _concept_for_review(conn, concept_id)
            current_version = planned_versions.setdefault(concept_id, _row_version(conn, concept_id))
            raw_version = row.get("row_version")
            version = int(raw_version) if raw_version not in (None, "") else None
            if version is not None and version != current_version:
                raise ValueError(f"row_version mismatch for {concept_id}: expected {current_version}, got {version}")
            new_status = _ACTION_TO_STATUS[action]
            planned_versions[concept_id] = current_version + 1
            validated.append(
                _ValidatedAction(
                    row_index=index,
                    row=row,
                    concept_id=concept_id,
                    action=action,
                    reviewer=reviewer,
                    reason=reason,
                    reason_code=reason_code,
                    row_version=version,
                    previous_status=concept["status"],
                    new_status=new_status,
                    new_row_version=current_version + 1,
                )
            )
            report_row.update(
                {
                    "import_status": "valid",
                    "new_status": new_status,
                    "new_row_version": str(current_version + 1),
                    "error_message": "",
                }
            )
        except ValueError as exc:
            message = str(exc)
            report_row.update({"import_status": "error", "new_status": "", "new_row_version": "", "error_message": message})
            if first_error is None:
                first_error = ValueError(message)
        report_rows.append(report_row)

    if first_error is not None:
        raise first_error
    return validated, report_rows, skipped


def import_review_actions(
    db_path: str | Path,
    input_path: str | Path,
    *,
    dry_run: bool = False,
    report_path: str | Path | None = None,
    write_back_path: str | Path | None = None,
) -> ImportReviewResult:
    init_db(db_path)
    path = Path(input_path)
    rows = list(_iter_action_rows(path))
    written_report_path: Path | None = None
    written_write_back_path: Path | None = None

    with connect(db_path) as conn:
        try:
            validated, report_rows, skipped = _validate_import_rows(conn, rows)
        except ValueError:
            if report_path is not None:
                # Re-run validation in report mode so callers get row-level diagnostics
                # while still raising the validation failure to prevent partial imports.
                report_rows = []
                planned_versions: dict[str, int] = {}
                for row in rows:
                    report_row = dict(row)
                    action = _action_from_row(row)
                    if action in {"", "inspect", "split"}:
                        report_row.update({"import_status": "skipped", "new_status": "", "new_row_version": "", "error_message": ""})
                        report_rows.append(report_row)
                        continue
                    try:
                        concept_id = (row.get("concept_id") or "").strip()
                        reviewer = (row.get("reviewer") or "").strip()
                        reason = _optional_text(row, "reason", "review_note")
                        reason_code = _optional_text(row, "reason_code")
                        _validate_action(action, reviewer, reason_code, reason)
                        concept = _concept_for_review(conn, concept_id)
                        current_version = planned_versions.setdefault(concept_id, _row_version(conn, concept_id))
                        raw_version = row.get("row_version")
                        version = int(raw_version) if raw_version not in (None, "") else None
                        if version is not None and version != current_version:
                            raise ValueError(
                                f"row_version mismatch for {concept_id}: expected {current_version}, got {version}"
                            )
                        planned_versions[concept_id] = current_version + 1
                        report_row.update(
                            {
                                "import_status": "valid",
                                "new_status": _ACTION_TO_STATUS[action],
                                "new_row_version": str(current_version + 1),
                                "error_message": "",
                            }
                        )
                    except ValueError as exc:
                        report_row.update(
                            {"import_status": "error", "new_status": "", "new_row_version": "", "error_message": str(exc)}
                        )
                    report_rows.append(report_row)
                written_report_path = _write_review_report(report_path, report_rows)
            raise

        if dry_run:
            if report_path is not None:
                written_report_path = _write_review_report(report_path, report_rows)
            return ImportReviewResult(
                actions_applied=0,
                rows_seen=len(rows),
                actions_valid=len(validated),
                actions_skipped=skipped,
                report_path=written_report_path,
            )

        applied_rows: list[dict[str, str]] = []
        by_index = {action.row_index: action for action in validated}
        actions_applied = 0
        for index, row in enumerate(rows, start=1):
            report_row = dict(row)
            action_plan = by_index.get(index)
            if action_plan is None:
                report_row.update({"import_status": "skipped", "new_status": "", "new_row_version": "", "error_message": ""})
                applied_rows.append(report_row)
                continue
            result = _apply_review_action_conn(
                conn,
                concept_id=action_plan.concept_id,
                action=action_plan.action,
                reviewer=action_plan.reviewer,
                reason=action_plan.reason,
                reason_code=action_plan.reason_code,
                row_version=action_plan.row_version,
            )
            actions_applied += 1
            report_row.update(
                {
                    "import_status": "applied",
                    "new_status": result.new_status,
                    "new_row_version": str(result.row_version),
                    "error_message": "",
                }
            )
            applied_rows.append(report_row)

    if report_path is not None:
        written_report_path = _write_review_report(report_path, applied_rows)
    if write_back_path is not None:
        written_write_back_path = _write_review_report(write_back_path, applied_rows)
    return ImportReviewResult(
        actions_applied=actions_applied,
        rows_seen=len(rows),
        actions_valid=len(validated),
        actions_skipped=skipped,
        report_path=written_report_path,
        write_back_path=written_write_back_path,
    )
