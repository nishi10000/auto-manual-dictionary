from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .anchors import normalize_text
from .db import connect, init_db


@dataclass(frozen=True, order=True)
class TermCandidate:
    lang: str
    term: str
    normalized_term: str
    term_type: str = "domain_phrase"


@dataclass(frozen=True)
class TermExtractionResult:
    terms_seen: int
    terms_created: int
    occurrences_created: int


JA_DOMAIN_TERMS = [
    "エンジン始動不良",
    "始動不良",
    "エンジンがかからない",
    "補機バッテリー",
    "バッテリー電圧",
    "締付トルク",
    "フロントハブナット",
    "ハブナット",
    "ブレーキフルード",
    "指定フルード",
    "リザーバ容量",
    "エア抜き順序",
    "再使用不可部品",
    "燃圧",
]

EN_DOMAIN_PHRASES = [
    "engine does not start",
    "auxiliary battery",
    "battery voltage",
    "tightening torque",
    "front hub nut",
    "hub nut",
    "brake fluid",
    "specified fluid",
    "reservoir capacity",
    "bleeding order",
    "fuel pressure",
    "non-reusable parts",
]

EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "before", "after",
    "do", "not", "check", "follow", "this", "that", "only", "page", "exists", "manual",
    "warning", "caution", "note", "symptom", "item", "standard", "specified", "temporarily",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_term(term: str, lang: str) -> str:
    normalized = normalize_text(term)
    if lang == "en":
        normalized = normalized.lower()
    return normalized.strip(" .,:;()[]{}")


def _add_candidate(seen: set[tuple[str, str]], candidates: list[TermCandidate], lang: str, term: str, term_type: str) -> None:
    normalized = normalize_term(term, lang)
    if not normalized:
        return
    key = (lang, normalized)
    if key in seen:
        return
    seen.add(key)
    candidates.append(TermCandidate(lang=lang, term=term.strip(), normalized_term=normalized, term_type=term_type))


def _extract_ja_terms(text: str) -> list[TermCandidate]:
    text = normalize_text(text)
    seen: set[tuple[str, str]] = set()
    candidates: list[TermCandidate] = []
    for term in sorted(JA_DOMAIN_TERMS, key=len, reverse=True):
        if term in text:
            _add_candidate(seen, candidates, "ja", term, "domain_phrase")

    # Conservative fallback: preserve compact automotive-looking Japanese noun compounds.
    for match in re.finditer(r"[一-龥ァ-ヴーA-Za-z0-9]{2,}(?:トルク|不良|電圧|容量|順序|部品|フルード|バッテリー|ナット|燃圧)", text):
        _add_candidate(seen, candidates, "ja", match.group(0), "regex_phrase")
    return sorted(candidates)


def _extract_en_terms(text: str) -> list[TermCandidate]:
    text = normalize_text(text)
    lower_text = text.lower()
    seen: set[tuple[str, str]] = set()
    candidates: list[TermCandidate] = []
    for phrase in sorted(EN_DOMAIN_PHRASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", lower_text):
            _add_candidate(seen, candidates, "en", phrase, "domain_phrase")

    tokens = re.findall(r"[A-Za-z][A-Za-z-]*", lower_text)
    for n in range(2, 5):
        for i in range(0, max(0, len(tokens) - n + 1)):
            window = tokens[i : i + n]
            if all(token in EN_STOPWORDS for token in window):
                continue
            if any(token in {"engine", "battery", "voltage", "torque", "fuel", "pressure", "hub", "nut", "fluid", "reservoir", "capacity"} for token in window):
                _add_candidate(seen, candidates, "en", " ".join(window), "regex_phrase")
    return sorted(candidates)


def extract_terms_from_text(lang: str, text: str) -> list[TermCandidate]:
    if lang == "ja":
        return _extract_ja_terms(text)
    if lang == "en":
        return _extract_en_terms(text)
    raise ValueError("lang must be 'ja' or 'en'")


def _upsert_term(conn, candidate: TermCandidate) -> tuple[int, bool]:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO terms(lang, term, normalized_term, term_type, status, created_at)
        VALUES (?, ?, ?, ?, 'candidate', ?)
        """,
        (candidate.lang, candidate.term, candidate.normalized_term, candidate.term_type, _now()),
    )
    row = conn.execute(
        "SELECT id FROM terms WHERE lang = ? AND normalized_term = ?",
        (candidate.lang, candidate.normalized_term),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"failed to upsert term: {candidate.normalized_term}")
    return int(row["id"]), cur.rowcount > 0


def _insert_occurrence(conn, *, term_id: int, document_id: int, block_id: int) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO term_occurrences(term_id, document_id, block_id, source, created_at)
        VALUES (?, ?, ?, 'block', ?)
        """,
        (term_id, document_id, block_id, _now()),
    )
    return cur.rowcount > 0


def extract_terms_to_db(*, db_path: str | Path) -> TermExtractionResult:
    init_db(db_path)
    terms_seen = 0
    terms_created = 0
    occurrences_created = 0
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT document_blocks.id AS block_id, document_blocks.document_id, document_blocks.text, documents.lang
            FROM document_blocks
            JOIN documents ON documents.id = document_blocks.document_id
            ORDER BY documents.lang, documents.path, document_blocks.block_index
            """
        ).fetchall()
        for row in rows:
            candidates = extract_terms_from_text(row["lang"], row["text"])
            terms_seen += len(candidates)
            for candidate in candidates:
                term_id, created = _upsert_term(conn, candidate)
                if created:
                    terms_created += 1
                if _insert_occurrence(conn, term_id=term_id, document_id=row["document_id"], block_id=row["block_id"]):
                    occurrences_created += 1
    return TermExtractionResult(
        terms_seen=terms_seen,
        terms_created=terms_created,
        occurrences_created=occurrences_created,
    )
