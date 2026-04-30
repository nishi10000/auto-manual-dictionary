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
    action = action.strip().lower()
    _validate_action(action, reviewer, reason_code, reason)
    with connect(db_path) as conn:
        concept = conn.execute(
            "SELECT id, concept_id, status FROM concepts WHERE concept_id = ?",
            (concept_id,),
        ).fetchone()
        if concept is None:
            raise ValueError(f"concept not found: {concept_id}")
        current_version = _row_version(conn, concept_id)
        if row_version is not None and int(row_version) != current_version:
            raise ValueError(
                f"row_version mismatch for {concept_id}: expected {current_version}, got {row_version}"
            )
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


def import_review_actions(db_path: str | Path, input_path: str | Path) -> ImportReviewResult:
    path = Path(input_path)
    rows_seen = 0
    actions_applied = 0
    for row in _iter_action_rows(path):
        rows_seen += 1
        action = (row.get("action") or row.get("recommended_action") or "").strip().lower()
        if action in {"", "inspect", "split"}:
            continue
        raw_version = row.get("row_version")
        version = int(raw_version) if raw_version not in (None, "") else None
        apply_review_action(
            db_path=db_path,
            concept_id=(row.get("concept_id") or "").strip(),
            action=action,
            reviewer=(row.get("reviewer") or "").strip(),
            reason=(row.get("reason") or row.get("review_note") or "").strip() or None,
            reason_code=(row.get("reason_code") or "").strip() or None,
            row_version=version,
        )
        actions_applied += 1
    return ImportReviewResult(actions_applied=actions_applied, rows_seen=rows_seen)
