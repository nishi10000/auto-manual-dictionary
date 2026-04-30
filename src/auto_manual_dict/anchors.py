from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, order=True)
class Anchor:
    anchor_type: str
    value: str
    normalized_value: str


DTC_RE = re.compile(r"\b(?:[PCBU][0-9A-F]{4})\b", re.IGNORECASE)
TORQUE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:N\s*[·.\- ]?\s*m|Nm)\b", re.IGNORECASE)
VOLTAGE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*V\b", re.IGNORECASE)
PART_NO_RE = re.compile(r"\b\d{5}-[A-Z0-9]{4,6}\b", re.IGNORECASE)
KPA_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*kPa\b", re.IGNORECASE)
LITER_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*L\b", re.IGNORECASE)


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _number(value: str) -> str:
    if "." in value:
        return value.rstrip("0").rstrip(".")
    return value


def _add(seen: set[tuple[str, str]], anchors: list[Anchor], anchor_type: str, value: str, normalized_value: str) -> None:
    key = (anchor_type, normalized_value)
    if key not in seen:
        seen.add(key)
        anchors.append(Anchor(anchor_type=anchor_type, value=value, normalized_value=normalized_value))


def extract_anchors(text: str, images: list[str] | None = None) -> list[Anchor]:
    text = normalize_text(text)
    anchors: list[Anchor] = []
    seen: set[tuple[str, str]] = set()

    for match in DTC_RE.finditer(text):
        value = match.group(0).upper()
        _add(seen, anchors, "dtc", match.group(0), value)

    for match in TORQUE_RE.finditer(text):
        value = f"{_number(match.group(1))} Nm"
        _add(seen, anchors, "torque", match.group(0), value)

    for match in VOLTAGE_RE.finditer(text):
        value = f"{_number(match.group(1))} V"
        _add(seen, anchors, "voltage", match.group(0), value)

    for match in PART_NO_RE.finditer(text):
        value = match.group(0).upper()
        _add(seen, anchors, "part_number", match.group(0), value)

    for match in KPA_RE.finditer(text):
        value = f"{_number(match.group(1))} kPa"
        _add(seen, anchors, "pressure", match.group(0), value)

    for match in LITER_RE.finditer(text):
        value = f"{_number(match.group(1))} L"
        _add(seen, anchors, "volume", match.group(0), value)

    for image in images or []:
        filename = PurePosixPath(image.replace("\\", "/")).name.lower()
        if filename:
            _add(seen, anchors, "image_name", image, filename)

    return sorted(anchors)
