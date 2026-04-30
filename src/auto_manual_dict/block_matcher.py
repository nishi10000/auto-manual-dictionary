from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect, init_db

ANCHOR_WEIGHTS = {
    "dtc": 0.35,
    "torque": 0.25,
    "voltage": 0.25,
    "part_number": 0.25,
    "pressure": 0.25,
    "volume": 0.25,
    "image_name": 0.20,
}


@dataclass(frozen=True)
class MatchScore:
    score: float
    evidence: dict[str, Any]


@dataclass(frozen=True)
class MatchResult:
    candidates_written: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _anchors_for_block(conn, block_id: int) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT anchor_type, normalized_value
        FROM anchors
        WHERE block_id = ?
        """,
        (block_id,),
    ).fetchall()
    anchors: dict[str, set[str]] = {}
    for row in rows:
        anchors.setdefault(row[0], set()).add(row[1])
    return anchors


def _block_row(conn, block_id: int) -> dict[str, Any]:
    cur = conn.execute(
        """
        SELECT document_blocks.*, documents.lang, documents.path
        FROM document_blocks
        JOIN documents ON documents.id = document_blocks.document_id
        WHERE document_blocks.id = ?
        """,
        (block_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"block not found: {block_id}")
    if isinstance(row, dict):
        return row
    return {description[0]: row[index] for index, description in enumerate(cur.description)}


def _heading_tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    # MVP: exact ASCII token overlap only. Cross-lingual semantic matching is a later layer.
    import re

    return {token.lower() for token in re.findall(r"[A-Za-z0-9]+", text) if len(token) >= 2}


def _table_shape(row) -> str | None:
    if row["block_type"] != "table_row":
        return None
    # Store only a coarse shape to avoid leaking full table content in evidence.
    cells = [part.strip() for part in row["text"].split() if part.strip()]
    return f"cells:{len(cells)}"


def score_block_pair(conn, ja_block_id: int, en_block_id: int) -> MatchScore:
    ja = _block_row(conn, ja_block_id)
    en = _block_row(conn, en_block_id)
    if ja["lang"] != "ja" or en["lang"] != "en":
        raise ValueError("score_block_pair expects ja_block_id then en_block_id")

    score = 0.0
    shared_anchors: dict[str, list[str]] = {}
    ja_anchors = _anchors_for_block(conn, ja_block_id)
    en_anchors = _anchors_for_block(conn, en_block_id)
    for anchor_type, weight in ANCHOR_WEIGHTS.items():
        shared = sorted(ja_anchors.get(anchor_type, set()) & en_anchors.get(anchor_type, set()))
        if shared:
            shared_anchors[anchor_type] = shared
            score += weight

    heading_overlap: list[str] = []
    ja_heading_tokens = _heading_tokens(ja["heading_path"])
    en_heading_tokens = _heading_tokens(en["heading_path"])
    if ja_heading_tokens and en_heading_tokens:
        heading_overlap = sorted(ja_heading_tokens & en_heading_tokens)
        if heading_overlap:
            score += 0.10

    table_shape_match = False
    if ja["block_type"] == "table_row" and en["block_type"] == "table_row":
        table_shape_match = _table_shape(ja) == _table_shape(en)
        if table_shape_match:
            score += 0.10

    score = round(min(1.0, max(0.0, score)), 6)
    evidence: dict[str, Any] = {
        "shared_anchors": shared_anchors,
        "heading_token_overlap": heading_overlap,
        "table_shape_match": table_shape_match,
        "scoring_version": "block_matcher_mvp_0.1",
    }
    return MatchScore(score=score, evidence=evidence)


def _candidate_blocks(conn, lang: str):
    return conn.execute(
        """
        SELECT document_blocks.id, document_blocks.document_id
        FROM document_blocks
        JOIN documents ON documents.id = document_blocks.document_id
        WHERE documents.lang = ?
        ORDER BY documents.path, document_blocks.block_index
        """,
        (lang,),
    ).fetchall()


def _upsert_candidate(conn, ja_block_id: int, en_block_id: int, score: float, evidence: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO block_match_candidates(ja_block_id, en_block_id, score, evidence_json, status, created_at)
        VALUES (?, ?, ?, ?, 'candidate', ?)
        ON CONFLICT(ja_block_id, en_block_id) DO UPDATE SET
          score = excluded.score,
          evidence_json = excluded.evidence_json
        """,
        (ja_block_id, en_block_id, score, json.dumps(evidence, ensure_ascii=False, sort_keys=True), _now()),
    )


def match_blocks(*, db_path: str | Path, min_score: float = 0.20, top_k_per_block: int = 5) -> MatchResult:
    init_db(db_path)
    candidates_written = 0
    with connect(db_path) as conn:
        ja_blocks = _candidate_blocks(conn, "ja")
        en_blocks = _candidate_blocks(conn, "en")
        for ja in ja_blocks:
            scored: list[tuple[float, int, dict[str, Any]]] = []
            for en in en_blocks:
                match = score_block_pair(conn, ja["id"], en["id"])
                if match.score >= min_score:
                    scored.append((match.score, en["id"], match.evidence))
            scored.sort(key=lambda item: (-item[0], item[1]))
            for score, en_block_id, evidence in scored[:top_k_per_block]:
                _upsert_candidate(conn, ja["id"], en_block_id, score, evidence)
                candidates_written += 1
    return MatchResult(candidates_written=candidates_written)
