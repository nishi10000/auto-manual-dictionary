from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect, init_db

CONFIDENCE_VERSION = "confidence_mvp_0.1"


@dataclass(frozen=True)
class ConfidenceUpdateResult:
    concepts_seen: int
    concepts_updated: int
    review_ready: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _concept_rows(conn):
    return conn.execute(
        """
        SELECT id, concept_id, status
        FROM concepts
        WHERE status != 'blocked'
        ORDER BY concept_id
        """
    ).fetchall()


def _review_allows_confirmed_consistency(conn, *, concept_public_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM review_actions
        WHERE target_type = 'concept'
          AND target_id = ?
          AND action IN ('approve', 'confirm')
          AND new_status = 'confirmed'
        LIMIT 1
        """,
        (concept_public_id,),
    ).fetchone()
    return row is not None


def _evidence_rows(conn, *, concept_row_id: int, confirmed_consistency_allowed: bool):
    rows = conn.execute(
        """
        SELECT evidence.*
        FROM evidence
        WHERE concept_id = ?
        ORDER BY is_negative_evidence, evidence_type, id
        """,
        (concept_row_id,),
    ).fetchall()
    if confirmed_consistency_allowed:
        return rows
    return [row for row in rows if row["evidence_type"] != "confirmed_consistency"]


def _safe_json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _has_anchor_signal(anchors: dict[str, Any]) -> bool:
    shared = anchors.get("shared_anchors")
    if isinstance(shared, dict):
        return any(bool(values) for values in shared.values())
    return False


def _has_heading_signal(anchors: dict[str, Any]) -> bool:
    overlap = anchors.get("heading_token_overlap")
    return bool(overlap)


def _has_table_signal(anchors: dict[str, Any]) -> bool:
    return bool(anchors.get("table_shape_match"))


def score_concept_evidence(evidence_rows: list[Any]) -> tuple[float, dict[str, Any]]:
    positive = [row for row in evidence_rows if int(row["is_negative_evidence"] or 0) == 0]
    negative = [row for row in evidence_rows if int(row["is_negative_evidence"] or 0) != 0]
    evidence_count = len(positive)
    evidence_types = {row["evidence_type"] for row in positive}
    positive_scores = [float(row["score"] or 0.0) for row in positive]
    max_evidence_score = max(positive_scores, default=0.0)
    avg_evidence_score = sum(positive_scores) / len(positive_scores) if positive_scores else 0.0

    anchor_hits = 0
    heading_hits = 0
    table_hits = 0
    for row in positive:
        anchors = _safe_json_loads(row["anchors_json"])
        if _has_anchor_signal(anchors):
            anchor_hits += 1
        if _has_heading_signal(anchors):
            heading_hits += 1
        if _has_table_signal(anchors):
            table_hits += 1

    # The MVP intentionally rewards diversity more than raw repeated count.
    section_score = min(0.30, max_evidence_score * 0.55)
    anchor_score = 0.24 if anchor_hits else 0.0
    diversity_score = min(0.22, max(0, len(evidence_types) - 1) * 0.22)
    frequency_score = min(0.16, max(0, evidence_count - 1) * 0.08)
    lexical_score = min(0.08, avg_evidence_score * 0.10)
    heading_score = 0.05 if heading_hits else 0.0
    table_alignment_score = 0.05 if table_hits else 0.0
    negative_evidence_penalty = min(0.45, len(negative) * 0.30 + sum(float(row["score"] or 0.0) for row in negative) * 0.10)
    safety_penalty = 0.0

    raw_score = (
        section_score
        + anchor_score
        + diversity_score
        + frequency_score
        + lexical_score
        + heading_score
        + table_alignment_score
        - negative_evidence_penalty
        - safety_penalty
    )
    final_score = round(min(1.0, max(0.0, raw_score)), 6)
    breakdown: dict[str, Any] = {
        "version": CONFIDENCE_VERSION,
        "evidence_count": evidence_count,
        "negative_evidence_count": len(negative),
        "evidence_type_count": len(evidence_types),
        "evidence_types": sorted(evidence_types),
        "max_evidence_score": round(max_evidence_score, 6),
        "average_evidence_score": round(avg_evidence_score, 6),
        "anchor_score": round(anchor_score, 6),
        "section_score": round(section_score, 6),
        "lexical_score": round(lexical_score, 6),
        "frequency_score": round(frequency_score, 6),
        "diversity_score": round(diversity_score, 6),
        "heading_score": round(heading_score, 6),
        "table_alignment_score": round(table_alignment_score, 6),
        "negative_evidence_penalty": round(negative_evidence_penalty, 6),
        "safety_penalty": round(safety_penalty, 6),
        "final_score": final_score,
    }
    return final_score, breakdown


def _target_status(*, current_status: str, confidence: float, review_ready_threshold: float) -> str:
    if current_status == "confirmed":
        return "confirmed"
    if current_status == "blocked":
        return "blocked"
    if confidence >= review_ready_threshold:
        return "review_ready"
    return "candidate"


def update_confidence(*, db_path: str | Path, review_ready_threshold: float = 0.85) -> ConfidenceUpdateResult:
    init_db(db_path)
    concepts_seen = 0
    concepts_updated = 0
    review_ready = 0
    with connect(db_path) as conn:
        for concept in _concept_rows(conn):
            concepts_seen += 1
            evidence = _evidence_rows(
                conn,
                concept_row_id=int(concept["id"]),
                confirmed_consistency_allowed=_review_allows_confirmed_consistency(
                    conn,
                    concept_public_id=concept["concept_id"],
                ),
            )
            confidence, breakdown = score_concept_evidence(list(evidence))
            status = _target_status(
                current_status=concept["status"],
                confidence=confidence,
                review_ready_threshold=review_ready_threshold,
            )
            if status == "review_ready":
                review_ready += 1
            cur = conn.execute(
                """
                UPDATE concepts
                SET confidence = ?,
                    confidence_json = ?,
                    confidence_version = ?,
                    status = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status != 'confirmed'
                """,
                (
                    confidence,
                    json.dumps(breakdown, ensure_ascii=False, sort_keys=True),
                    CONFIDENCE_VERSION,
                    status,
                    _now(),
                    concept["id"],
                ),
            )
            if cur.rowcount > 0:
                concepts_updated += 1
    return ConfidenceUpdateResult(
        concepts_seen=concepts_seen,
        concepts_updated=concepts_updated,
        review_ready=review_ready,
    )
