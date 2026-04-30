from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .anchors import extract_anchors
from .db import SCHEMA_VERSION, connect, init_db
from .html_extract import ExtractedBlock, extract_html


@dataclass(frozen=True)
class IngestResult:
    documents_seen: int
    documents_inserted: int
    documents_updated: int
    blocks_written: int
    anchors_written: int
    errors: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _html_files(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".html", ".htm"})


def _delete_derived_matches_for_document(conn, document_id: int) -> None:
    # Existing match candidates may point at block IDs that are about to be
    # replaced. Delete them before replacing blocks so content updates do not
    # violate foreign keys or leave stale evidence candidates.
    conn.execute(
        """
        DELETE FROM block_match_candidates
        WHERE ja_block_id IN (SELECT id FROM document_blocks WHERE document_id = ?)
           OR en_block_id IN (SELECT id FROM document_blocks WHERE document_id = ?)
        """,
        (document_id, document_id),
    )
    conn.execute(
        "DELETE FROM page_match_candidates WHERE ja_document_id = ? OR en_document_id = ?",
        (document_id, document_id),
    )


def _upsert_document(
    conn,
    *,
    lang: str,
    rel_path: str,
    sha256: str,
    title: str | None,
    text_excerpt: str,
    source_html: str,
) -> tuple[int, str]:
    """Create or update a document.

    Returns `(document_id, state)` where state is one of:
    - `inserted`: new document row created
    - `unchanged`: same path and sha256 already present; extracted rows are kept stable
    - `metadata_updated`: same content, but document metadata was backfilled
    - `updated`: content changed; dependent extracted rows are replaced
    """
    now = _now()
    existing = conn.execute(
        "SELECT id, sha256, source_html FROM documents WHERE lang = ? AND path = ?",
        (lang, rel_path),
    ).fetchone()
    if existing is None:
        cur = conn.execute(
            """
            INSERT INTO documents(lang, path, sha256, title, text_excerpt, source_html, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (lang, rel_path, sha256, title, text_excerpt, source_html, now, now),
        )
        return int(cur.lastrowid), "inserted"

    if existing["sha256"] == sha256:
        if existing["source_html"] is None:
            conn.execute(
                """
                UPDATE documents
                SET title = ?, text_excerpt = ?, source_html = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, text_excerpt, source_html, now, existing["id"]),
            )
            return int(existing["id"]), "metadata_updated"
        return int(existing["id"]), "unchanged"

    conn.execute(
        """
        UPDATE documents
        SET sha256 = ?, title = ?, text_excerpt = ?, source_html = ?, updated_at = ?
        WHERE id = ?
        """,
        (sha256, title, text_excerpt, source_html, now, existing["id"]),
    )
    # Replace dependent extracted data only when content changed. This keeps block
    # ids stable for unchanged re-ingest runs and protects future evidence links.
    _delete_derived_matches_for_document(conn, int(existing["id"]))
    conn.execute("DELETE FROM anchors WHERE document_id = ?", (existing["id"],))
    conn.execute("DELETE FROM document_blocks WHERE document_id = ?", (existing["id"],))
    return int(existing["id"]), "updated"


def _insert_block(conn, document_id: int, block: ExtractedBlock) -> int:
    cur = conn.execute(
        """
        INSERT INTO document_blocks(
          document_id, block_type, block_index, heading_path, dom_path,
          raw_fragment_hash, text, normalized_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            block.block_type,
            block.block_index,
            block.heading_path,
            block.dom_path,
            block.raw_fragment_hash,
            block.text,
            block.normalized_text,
        ),
    )
    return int(cur.lastrowid)


def _insert_anchor(conn, *, document_id: int, block_id: int | None, anchor_type: str, value: str, normalized_value: str) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO anchors(document_id, block_id, anchor_type, value, normalized_value)
        VALUES (?, ?, ?, ?, ?)
        """,
        (document_id, block_id, anchor_type, value, normalized_value),
    )
    return cur.rowcount > 0


def ingest_directory(*, lang: str, input_dir: str | Path, db_path: str | Path) -> IngestResult:
    if lang not in {"ja", "en"}:
        raise ValueError("lang must be 'ja' or 'en'")
    input_dir = Path(input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"input directory does not exist: {input_dir}")

    init_db(db_path)
    files = _html_files(input_dir)
    run_id = str(uuid.uuid4())
    started_at = _now()

    documents_inserted = 0
    documents_updated = 0
    blocks_written = 0
    anchors_written = 0
    errors = 0

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ingestion_runs(run_id, lang, input_path, started_at, documents_seen, schema_version)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, lang, str(input_dir), started_at, len(files), SCHEMA_VERSION),
        )
        for file_path in files:
            try:
                data = file_path.read_bytes()
                html = data.decode("utf-8", errors="replace")
                extracted = extract_html(html)
                rel_path = file_path.relative_to(input_dir).as_posix()
                excerpt = " ".join(block.text for block in extracted.blocks)[:500]
                document_id, state = _upsert_document(
                    conn,
                    lang=lang,
                    rel_path=rel_path,
                    sha256=_sha256_bytes(data),
                    title=extracted.title,
                    text_excerpt=excerpt,
                    source_html=html,
                )
                if state == "inserted":
                    documents_inserted += 1
                elif state in {"updated", "metadata_updated"}:
                    documents_updated += 1
                    if state == "metadata_updated":
                        continue
                else:
                    continue

                document_text_parts: list[str] = []
                for block in extracted.blocks:
                    block_id = _insert_block(conn, document_id, block)
                    blocks_written += 1
                    document_text_parts.append(block.text)
                    for anchor in extract_anchors(block.text):
                        if _insert_anchor(
                            conn,
                            document_id=document_id,
                            block_id=block_id,
                            anchor_type=anchor.anchor_type,
                            value=anchor.value,
                            normalized_value=anchor.normalized_value,
                        ):
                            anchors_written += 1

                for anchor in extract_anchors(" ".join(document_text_parts), images=extracted.images):
                    if _insert_anchor(
                        conn,
                        document_id=document_id,
                        block_id=None,
                        anchor_type=anchor.anchor_type,
                        value=anchor.value,
                        normalized_value=anchor.normalized_value,
                    ):
                        anchors_written += 1
            except Exception:
                # Do not log source HTML snippets here; caller may report aggregate errors.
                errors += 1

        conn.execute(
            """
            UPDATE ingestion_runs
            SET completed_at = ?, documents_inserted = ?, documents_updated = ?, errors = ?
            WHERE run_id = ?
            """,
            (_now(), documents_inserted, documents_updated, errors, run_id),
        )

    return IngestResult(
        documents_seen=len(files),
        documents_inserted=documents_inserted,
        documents_updated=documents_updated,
        blocks_written=blocks_written,
        anchors_written=anchors_written,
        errors=errors,
    )
