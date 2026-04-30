from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect, init_db

EXTRACTOR_NAME = "concept_builder"
EXTRACTOR_VERSION = "concept_builder_mvp_0.1"


@dataclass(frozen=True)
class ConceptBuildResult:
    concepts_seen: int
    concepts_created: int
    concept_terms_created: int
    evidence_created: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_concept_id(*, category: str, ja_normalized_term: str, en_normalized_term: str) -> str:
    key = f"{category}|ja:{ja_normalized_term}|en:{en_normalized_term}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"concept:{category}:{digest}"


def _terms_for_block(conn, *, block_id: int, lang: str):
    return conn.execute(
        """
        SELECT terms.id, terms.term, terms.normalized_term, terms.term_type
        FROM term_occurrences
        JOIN terms ON terms.id = term_occurrences.term_id
        WHERE term_occurrences.block_id = ?
          AND terms.lang = ?
          AND terms.status != 'blocked'
        ORDER BY terms.normalized_term
        """,
        (block_id, lang),
    ).fetchall()


def _matched_blocks(conn, *, min_match_score: float):
    return conn.execute(
        """
        SELECT bmc.id AS match_id, bmc.ja_block_id, bmc.en_block_id, bmc.score, bmc.evidence_json,
               ja.document_id AS ja_document_id, ja.text AS ja_context,
               en.document_id AS en_document_id, en.text AS en_context
        FROM block_match_candidates bmc
        JOIN document_blocks ja ON ja.id = bmc.ja_block_id
        JOIN document_blocks en ON en.id = bmc.en_block_id
        WHERE bmc.score >= ?
          AND bmc.status != 'blocked'
        ORDER BY bmc.score DESC, bmc.ja_block_id, bmc.en_block_id
        """,
        (min_match_score,),
    ).fetchall()


def _infer_category(ja_term: Any, en_term: Any) -> str:
    # MVP: keep category conservative and stable until later classifiers/review are added.
    return "unknown"


def _upsert_concept(conn, *, concept_id: str, category: str, ja_label: str, en_label: str, score: float) -> tuple[int, bool]:
    now = _now()
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO concepts(
          concept_id, concept_type, category, canonical_label_ja, canonical_label_en,
          confidence, confidence_json, confidence_version, status,
          safe_for_query_expansion, safe_for_answer_generation,
          created_at, updated_at
        )
        VALUES (?, 'term_pair', ?, ?, ?, ?, ?, ?, 'candidate', 0, 0, ?, ?)
        """,
        (
            concept_id,
            category,
            ja_label,
            en_label,
            score,
            json.dumps({"initial_block_match_score": score}, ensure_ascii=False, sort_keys=True),
            EXTRACTOR_VERSION,
            now,
            now,
        ),
    )
    created = cur.rowcount > 0
    if not created:
        conn.execute(
            """
            UPDATE concepts
            SET confidence = MAX(confidence, ?),
                updated_at = ?,
                confidence_json = CASE
                  WHEN confidence <= ? THEN ?
                  ELSE confidence_json
                END,
                confidence_version = COALESCE(confidence_version, ?)
            WHERE concept_id = ?
              AND status != 'confirmed'
            """,
            (
                score,
                now,
                score,
                json.dumps({"initial_block_match_score": score}, ensure_ascii=False, sort_keys=True),
                EXTRACTOR_VERSION,
                concept_id,
            ),
        )
    row = conn.execute("SELECT id FROM concepts WHERE concept_id = ?", (concept_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"failed to upsert concept: {concept_id}")
    return int(row["id"]), created


def _insert_concept_term(conn, *, concept_row_id: int, term_id: int, confidence: float) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO concept_terms(concept_id, term_id, role, confidence, status)
        VALUES (?, ?, 'label', ?, 'candidate')
        """,
        (concept_row_id, term_id, confidence),
    )
    if cur.rowcount == 0:
        conn.execute(
            """
            UPDATE concept_terms
            SET confidence = MAX(confidence, ?)
            WHERE concept_id = ? AND term_id = ?
            """,
            (confidence, concept_row_id, term_id),
        )
    return cur.rowcount > 0


def _insert_evidence(
    conn,
    *,
    concept_row_id: int,
    ja_term_id: int,
    en_term_id: int,
    match_row: Any,
) -> bool:
    anchors_json = match_row["evidence_json"]
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO evidence(
          concept_id, ja_term_id, en_term_id,
          ja_document_id, en_document_id, ja_block_id, en_block_id,
          evidence_type, score, is_negative_evidence,
          extractor_name, extractor_version, anchors_json,
          ja_context, en_context, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'matched_block_terms', ?, 0, ?, ?, ?, ?, ?, ?)
        """,
        (
            concept_row_id,
            ja_term_id,
            en_term_id,
            match_row["ja_document_id"],
            match_row["en_document_id"],
            match_row["ja_block_id"],
            match_row["en_block_id"],
            float(match_row["score"]),
            EXTRACTOR_NAME,
            EXTRACTOR_VERSION,
            anchors_json,
            match_row["ja_context"],
            match_row["en_context"],
            _now(),
        ),
    )
    return cur.rowcount > 0


def build_concepts(*, db_path: str | Path, min_match_score: float = 0.25) -> ConceptBuildResult:
    init_db(db_path)
    concepts_seen = 0
    concepts_created = 0
    concept_terms_created = 0
    evidence_created = 0
    with connect(db_path) as conn:
        for match_row in _matched_blocks(conn, min_match_score=min_match_score):
            ja_terms = _terms_for_block(conn, block_id=match_row["ja_block_id"], lang="ja")
            en_terms = _terms_for_block(conn, block_id=match_row["en_block_id"], lang="en")
            for ja_term in ja_terms:
                for en_term in en_terms:
                    category = _infer_category(ja_term, en_term)
                    concept_public_id = stable_concept_id(
                        category=category,
                        ja_normalized_term=ja_term["normalized_term"],
                        en_normalized_term=en_term["normalized_term"],
                    )
                    concepts_seen += 1
                    concept_row_id, created = _upsert_concept(
                        conn,
                        concept_id=concept_public_id,
                        category=category,
                        ja_label=ja_term["term"],
                        en_label=en_term["term"],
                        score=float(match_row["score"]),
                    )
                    if created:
                        concepts_created += 1
                    if _insert_concept_term(
                        conn,
                        concept_row_id=concept_row_id,
                        term_id=int(ja_term["id"]),
                        confidence=float(match_row["score"]),
                    ):
                        concept_terms_created += 1
                    if _insert_concept_term(
                        conn,
                        concept_row_id=concept_row_id,
                        term_id=int(en_term["id"]),
                        confidence=float(match_row["score"]),
                    ):
                        concept_terms_created += 1
                    if _insert_evidence(
                        conn,
                        concept_row_id=concept_row_id,
                        ja_term_id=int(ja_term["id"]),
                        en_term_id=int(en_term["id"]),
                        match_row=match_row,
                    ):
                        evidence_created += 1
    return ConceptBuildResult(
        concepts_seen=concepts_seen,
        concepts_created=concepts_created,
        concept_terms_created=concept_terms_created,
        evidence_created=evidence_created,
    )
