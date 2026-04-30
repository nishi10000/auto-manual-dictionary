from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from .anchors import normalize_text


@dataclass(frozen=True)
class ExtractedBlock:
    block_type: str
    block_index: int
    text: str
    heading_path: str | None = None
    dom_path: str | None = None
    raw_fragment_hash: str | None = None
    normalized_text: str | None = None


@dataclass(frozen=True)
class ExtractedHtml:
    title: str | None
    headings: list[str]
    blocks: list[ExtractedBlock]
    images: list[str] = field(default_factory=list)


SAFETY_CLASS_TYPES = {
    "warning": "warning",
    "caution": "caution",
    "note": "note",
    "prohibition": "prohibition",
    "prohibited": "prohibition",
}

SAFETY_TEXT_PATTERNS = [
    (re.compile(r"^(警告|WARNING)[:：]?", re.IGNORECASE), "warning"),
    (re.compile(r"^(注意|CAUTION)[:：]?", re.IGNORECASE), "caution"),
    (re.compile(r"^(参考|NOTE)[:：]?", re.IGNORECASE), "note"),
    (re.compile(r"^(禁止|PROHIBITED|PROHIBITION)[:：]?", re.IGNORECASE), "prohibition"),
]

BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr", "div"}


def _text_of(tag: Tag) -> str:
    return normalize_text(tag.get_text(" ", strip=True))


def _dom_path(tag: Tag) -> str:
    parts: list[str] = []
    node = tag
    while isinstance(node, Tag) and node.name not in {"[document]", None}:
        parts.append(node.name)
        parent = node.parent
        node = parent if isinstance(parent, Tag) else None  # type: ignore[assignment]
    return "/".join(reversed(parts))


def _raw_hash(tag: Tag) -> str:
    return hashlib.sha256(str(tag).encode("utf-8", errors="replace")).hexdigest()


def _safety_type(tag: Tag, text: str) -> str | None:
    classes = {str(c).lower() for c in tag.get("class", [])}
    for class_name in classes:
        if class_name in SAFETY_CLASS_TYPES:
            return SAFETY_CLASS_TYPES[class_name]
    lower_name = tag.name.lower()
    if lower_name in SAFETY_CLASS_TYPES:
        return SAFETY_CLASS_TYPES[lower_name]
    for pattern, block_type in SAFETY_TEXT_PATTERNS:
        if pattern.search(text):
            return block_type
    return None


def _block_type(tag: Tag, text: str) -> str:
    safety = _safety_type(tag, text)
    if safety:
        return safety
    if re.fullmatch(r"h[1-6]", tag.name or ""):
        return "heading"
    if tag.name == "tr":
        return "table_row"
    if tag.name == "li":
        return "procedure" if tag.find_parent("ol") else "list_item"
    if tag.name == "p":
        return "paragraph"
    return "block"


def extract_html(html: str) -> ExtractedHtml:
    soup = BeautifulSoup(html, "lxml")
    for unwanted in soup(["script", "style"]):
        unwanted.decompose()

    title_text = None
    if soup.title and soup.title.string:
        title_text = normalize_text(soup.title.string)

    headings: list[str] = []
    current_headings: list[str] = []
    blocks: list[ExtractedBlock] = []
    seen_fragments: set[str] = set()

    body = soup.body or soup
    for tag in body.find_all(BLOCK_TAGS):
        text = _text_of(tag)
        if not text:
            continue
        # Avoid double-counting container divs that only repeat child block text,
        # except explicit safety divs where class/text carries meaning.
        safety = _safety_type(tag, text)
        if tag.name == "div" and not safety and tag.find(BLOCK_TAGS):
            continue

        raw_hash = _raw_hash(tag)
        if raw_hash in seen_fragments:
            continue
        seen_fragments.add(raw_hash)

        block_type = _block_type(tag, text)
        if block_type == "heading":
            level = int(tag.name[1])
            current_headings = current_headings[: level - 1]
            current_headings.append(text)
            headings.append(text)
        heading_path = " > ".join(current_headings) if current_headings else None
        blocks.append(
            ExtractedBlock(
                block_type=block_type,
                block_index=len(blocks),
                text=text,
                heading_path=heading_path,
                dom_path=_dom_path(tag),
                raw_fragment_hash=raw_hash,
                normalized_text=normalize_text(text),
            )
        )

    images = [src for src in (img.get("src") for img in soup.find_all("img")) if src]
    return ExtractedHtml(title=title_text, headings=headings, blocks=blocks, images=images)
