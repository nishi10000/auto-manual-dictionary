from __future__ import annotations

import csv
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .db import connect, init_db


@dataclass(frozen=True)
class ExportResult:
    rows_exported: int
    out_path: Path
    export_batch_id: str | None = None


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _row_version(conn: sqlite3.Connection, concept_public_id: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM review_actions WHERE target_type = 'concept' AND target_id = ?",
            (concept_public_id,),
        ).fetchone()[0]
    )


def _terms_for_concept(conn: sqlite3.Connection, concept_pk: int, lang: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT t.term
        FROM concept_terms ct
        JOIN terms t ON t.id = ct.term_id
        WHERE ct.concept_id = ? AND t.lang = ?
        ORDER BY CASE ct.role WHEN 'primary' THEN 0 WHEN 'label' THEN 1 ELSE 2 END, t.term
        """,
        (concept_pk, lang),
    ).fetchall()
    return [row[0] for row in rows]


def _evidence_for_concept(conn: sqlite3.Connection, concept_pk: int) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT e.id, e.evidence_type, e.score, e.is_negative_evidence, e.anchors_json,
               e.ja_context, e.en_context,
               jd.path AS ja_source_path, ed.path AS en_source_path
        FROM evidence e
        LEFT JOIN documents jd ON jd.id = e.ja_document_id
        LEFT JOIN documents ed ON ed.id = e.en_document_id
        WHERE e.concept_id = ?
        ORDER BY e.score DESC, e.id ASC
        """,
        (concept_pk,),
    ).fetchall()
    evidence_ids = [int(row["id"]) for row in rows]
    evidence_types = sorted({row["evidence_type"] for row in rows})
    anchors: list[Any] = []
    source_files: set[str] = set()
    for row in rows:
        loaded = _json_loads(row["anchors_json"], [])
        if loaded:
            anchors.append(loaded)
        if row["ja_source_path"]:
            source_files.add(row["ja_source_path"])
        if row["en_source_path"]:
            source_files.add(row["en_source_path"])
    sample = rows[0] if rows else None
    summary = {
        "count": len(rows),
        "negative_count": sum(1 for row in rows if row["is_negative_evidence"]),
        "types": evidence_types,
        "max_score": max([float(row["score"]) for row in rows], default=0.0),
    }
    return {
        "evidence_ids": evidence_ids,
        "evidence_types": evidence_types,
        "evidence_summary": summary,
        "sample_ja_context": sample["ja_context"] if sample else "",
        "sample_en_context": sample["en_context"] if sample else "",
        "anchors": anchors,
        "source_files": sorted(source_files),
    }


def _recommend_action(confidence: float, evidence_count: int, negative_count: int) -> str:
    if negative_count > 0:
        return "inspect"
    if confidence >= 0.85 and evidence_count > 0:
        return "approve"
    if confidence >= 0.40 and evidence_count > 0:
        return "inspect"
    return "inspect"


def _review_rows(conn: sqlite3.Connection, *, status: str) -> list[dict[str, str]]:
    concepts = conn.execute(
        """
        SELECT id, concept_id, category, confidence, confidence_json, status
        FROM concepts
        WHERE status = ?
        ORDER BY confidence DESC, concept_id ASC
        """,
        (status,),
    ).fetchall()
    export_batch_id = str(uuid.uuid4())
    rows: list[dict[str, str]] = []
    for concept in concepts:
        concept_pk = int(concept["id"])
        evidence = _evidence_for_concept(conn, concept_pk)
        evidence_summary = evidence["evidence_summary"]
        row = {
            "concept_id": concept["concept_id"],
            "category": concept["category"] or "",
            "confidence": f"{float(concept['confidence']):.6f}",
            "confidence_json": concept["confidence_json"] or "{}",
            "status": concept["status"],
            "ja_terms": " | ".join(_terms_for_concept(conn, concept_pk, "ja")),
            "en_terms": " | ".join(_terms_for_concept(conn, concept_pk, "en")),
            "evidence_count": str(evidence_summary["count"]),
            "evidence_ids": _json_dumps(evidence["evidence_ids"]),
            "evidence_types": " | ".join(evidence["evidence_types"]),
            "evidence_summary": _json_dumps(evidence_summary),
            "sample_ja_context": evidence["sample_ja_context"] or "",
            "sample_en_context": evidence["sample_en_context"] or "",
            "anchors": _json_dumps(evidence["anchors"]),
            "source_files": " | ".join(evidence["source_files"]),
            "recommended_action": _recommend_action(
                float(concept["confidence"]),
                int(evidence_summary["count"]),
                int(evidence_summary["negative_count"]),
            ),
            "action": "",
            "reviewer": "",
            "reason": "",
            "reason_code": "",
            "review_note": "",
            "row_version": str(_row_version(conn, concept["concept_id"])),
            "export_batch_id": export_batch_id,
        }
        rows.append(row)
    return rows


REVIEW_COLUMNS = [
    "concept_id",
    "category",
    "confidence",
    "confidence_json",
    "status",
    "ja_terms",
    "en_terms",
    "evidence_count",
    "evidence_ids",
    "evidence_types",
    "evidence_summary",
    "sample_ja_context",
    "sample_en_context",
    "anchors",
    "source_files",
    "recommended_action",
    "action",
    "reviewer",
    "reason",
    "reason_code",
    "review_note",
    "row_version",
    "export_batch_id",
]


def export_review_queue(db_path: str | Path, out_path: str | Path, fmt: str = "csv", status: str = "review_ready") -> ExportResult:
    init_db(db_path)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        rows = _review_rows(conn, status=status)
    if fmt == "csv":
        with out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    elif fmt == "jsonl":
        with out.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(_json_dumps(row) + "\n")
    else:
        raise ValueError(f"unsupported review export format: {fmt}")
    batch_id = rows[0]["export_batch_id"] if rows else None
    return ExportResult(rows_exported=len(rows), out_path=out, export_batch_id=batch_id)


def _dictionary_rows(conn: sqlite3.Connection, *, safety_column: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT id, concept_id, category, canonical_label_ja, canonical_label_en,
               confidence, confidence_json, status, safe_for_query_expansion,
               safe_for_answer_generation, definition_note, scope_note, notes
        FROM concepts
        WHERE status = 'confirmed'
    """
    params: tuple[Any, ...] = ()
    if safety_column is not None:
        sql += f" AND {safety_column} = 1"
    sql += " ORDER BY concept_id ASC"
    rows = []
    for concept in conn.execute(sql, params).fetchall():
        concept_pk = int(concept["id"])
        rows.append(
            {
                "concept_id": concept["concept_id"],
                "category": concept["category"],
                "canonical_label_ja": concept["canonical_label_ja"],
                "canonical_label_en": concept["canonical_label_en"],
                "ja_terms": _terms_for_concept(conn, concept_pk, "ja"),
                "en_terms": _terms_for_concept(conn, concept_pk, "en"),
                "confidence": float(concept["confidence"]),
                "confidence_json": _json_loads(concept["confidence_json"], {}),
                "status": concept["status"],
                "safe_for_query_expansion": bool(concept["safe_for_query_expansion"]),
                "safe_for_answer_generation": bool(concept["safe_for_answer_generation"]),
                "definition_note": concept["definition_note"],
                "scope_note": concept["scope_note"],
                "notes": concept["notes"],
                "row_version": _row_version(conn, concept["concept_id"]),
            }
        )
    return rows


def _write_dict_rows(rows: list[dict[str, Any]], out: Path, fmt: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jsonl":
        with out.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(_json_dumps(row) + "\n")
        return
    if fmt == "csv":
        fieldnames = [
            "concept_id", "category", "canonical_label_ja", "canonical_label_en",
            "ja_terms", "en_terms", "confidence", "status",
            "safe_for_query_expansion", "safe_for_answer_generation", "row_version",
        ]
        with out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writable = dict(row)
                writable["ja_terms"] = " | ".join(row["ja_terms"])
                writable["en_terms"] = " | ".join(row["en_terms"])
                writer.writerow({key: writable.get(key, "") for key in fieldnames})
        return
    raise ValueError(f"unsupported dictionary export format: {fmt}")


def export_dictionary(db_path: str | Path, out_path: str | Path, fmt: str = "jsonl") -> ExportResult:
    init_db(db_path)
    out = Path(out_path)
    with connect(db_path) as conn:
        rows = _dictionary_rows(conn)
    _write_dict_rows(rows, out, fmt)
    return ExportResult(rows_exported=len(rows), out_path=out)


def export_query_expansion(db_path: str | Path, out_path: str | Path, fmt: str = "jsonl") -> ExportResult:
    init_db(db_path)
    out = Path(out_path)
    with connect(db_path) as conn:
        rows = _dictionary_rows(conn, safety_column="safe_for_query_expansion")
    _write_dict_rows(rows, out, fmt)
    return ExportResult(rows_exported=len(rows), out_path=out)


def export_answer_generation(db_path: str | Path, out_path: str | Path, fmt: str = "jsonl") -> ExportResult:
    init_db(db_path)
    out = Path(out_path)
    with connect(db_path) as conn:
        rows = _dictionary_rows(conn, safety_column="safe_for_answer_generation")
    _write_dict_rows(rows, out, fmt)
    return ExportResult(rows_exported=len(rows), out_path=out)
