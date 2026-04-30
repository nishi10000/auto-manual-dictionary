from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .block_matcher import ANCHOR_WEIGHTS, MatchScore
from .db import connect, init_db


@dataclass(frozen=True)
class PageMatchResult:
    candidates_written: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _document_row(conn, document_id: int) -> dict[str, Any]:
    cur = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"document not found: {document_id}")
    if isinstance(row, dict):
        return row
    return {description[0]: row[index] for index, description in enumerate(cur.description)}


def _anchors_for_document(conn, document_id: int) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT anchor_type, normalized_value
        FROM anchors
        WHERE document_id = ?
        """,
        (document_id,),
    ).fetchall()
    anchors: dict[str, set[str]] = {}
    for row in rows:
        anchors.setdefault(row[0], set()).add(row[1])
    return anchors


def score_page_pair(conn, ja_document_id: int, en_document_id: int) -> MatchScore:
    ja = _document_row(conn, ja_document_id)
    en = _document_row(conn, en_document_id)
    if ja["lang"] != "ja" or en["lang"] != "en":
        raise ValueError("score_page_pair expects ja_document_id then en_document_id")

    ja_anchors = _anchors_for_document(conn, ja_document_id)
    en_anchors = _anchors_for_document(conn, en_document_id)
    score = 0.0
    shared_anchors: dict[str, list[str]] = {}
    for anchor_type, weight in ANCHOR_WEIGHTS.items():
        shared = sorted(ja_anchors.get(anchor_type, set()) & en_anchors.get(anchor_type, set()))
        if shared:
            shared_anchors[anchor_type] = shared
            score += weight

    score = round(min(1.0, max(0.0, score)), 6)
    return MatchScore(
        score=score,
        evidence={
            "shared_anchors": shared_anchors,
            "match_scope": "document",
            "scoring_version": "page_matcher_mvp_0.1",
        },
    )


def _documents(conn, lang: str):
    return conn.execute("SELECT id FROM documents WHERE lang = ? ORDER BY path", (lang,)).fetchall()


def _upsert_candidate(conn, ja_document_id: int, en_document_id: int, score: float, evidence: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO page_match_candidates(
          ja_document_id, en_document_id, score, match_type, evidence_json, status
        ) VALUES (?, ?, ?, 'supplemental_anchor_score', ?, 'candidate')
        ON CONFLICT(ja_document_id, en_document_id) DO UPDATE SET
          score = excluded.score,
          match_type = excluded.match_type,
          evidence_json = excluded.evidence_json
        """,
        (ja_document_id, en_document_id, score, json.dumps(evidence, ensure_ascii=False, sort_keys=True)),
    )


def match_pages(*, db_path: str | Path, min_score: float = 0.25, top_k_per_document: int = 5) -> PageMatchResult:
    init_db(db_path)
    candidates_written = 0
    with connect(db_path) as conn:
        ja_docs = _documents(conn, "ja")
        en_docs = _documents(conn, "en")
        for ja in ja_docs:
            scored: list[tuple[float, int, dict[str, Any]]] = []
            for en in en_docs:
                match = score_page_pair(conn, ja["id"], en["id"])
                if match.score >= min_score:
                    scored.append((match.score, en["id"], match.evidence))
            scored.sort(key=lambda item: (-item[0], item[1]))
            for score, en_document_id, evidence in scored[:top_k_per_document]:
                _upsert_candidate(conn, ja["id"], en_document_id, score, evidence)
                candidates_written += 1
    return PageMatchResult(candidates_written=candidates_written)
