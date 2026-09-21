"""Deterministic prooflink validation against a permit document bundle."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

from core.schemas import Finding, Prooflink


_LOCATION = re.compile(r"^(page|row):([1-9][0-9]*)$")


@dataclass(frozen=True, slots=True)
class ProoflinkCheck:
    prooflink: Prooflink
    valid: bool
    reason: str


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def _resolve_source(permit_dir: Path, source_id: str) -> tuple[Path | None, str | None]:
    if source_id.startswith("mock://"):
        return None, "mock registry references are not document prooflinks"
    candidate = Path(source_id)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None, "source_id must be a relative path inside the permit bundle"
    exact = (permit_dir / candidate).resolve()
    root = permit_dir.resolve()
    if root != exact and root not in exact.parents:
        return None, "source_id escapes the permit bundle"
    if exact.is_file():
        return exact, None
    matches = [path for path in permit_dir.rglob(candidate.name) if path.is_file()]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, "source_id is ambiguous inside the permit bundle"
    return None, "source_id does not exist inside the permit bundle"


def _read_location(path: Path, kind: str, index: int) -> tuple[str | None, str | None]:
    if kind == "page":
        if path.suffix.casefold() != ".pdf":
            return None, "page locations require a PDF source"
        try:
            with fitz.open(path) as document:
                if index > document.page_count:
                    return None, f"page {index} does not exist"
                return document.load_page(index - 1).get_text(), None
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            return None, f"PDF cannot be read: {exc}"

    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        return None, f"row source cannot be read as UTF-8 text: {exc}"
    if index > len(lines):
        return None, f"row {index} does not exist"
    return lines[index - 1], None


def validate_prooflink(prooflink: Prooflink, permit_dir: str | Path) -> ProoflinkCheck:
    root = Path(permit_dir)
    if not root.is_dir():
        return ProoflinkCheck(prooflink, False, "permit bundle directory does not exist")
    match = _LOCATION.fullmatch(prooflink.location)
    if match is None:
        return ProoflinkCheck(prooflink, False, "location must be page:N or row:N")
    source, error = _resolve_source(root, prooflink.source_id)
    if error is not None or source is None:
        return ProoflinkCheck(prooflink, False, error or "source cannot be resolved")
    content, error = _read_location(source, match.group(1), int(match.group(2)))
    if error is not None or content is None:
        return ProoflinkCheck(prooflink, False, error or "location cannot be read")
    if _normalize(prooflink.quote) not in _normalize(content):
        return ProoflinkCheck(prooflink, False, "quote is not present at the referenced location")
    return ProoflinkCheck(prooflink, True, "ok")


def validate_finding(finding: Finding, permit_dir: str | Path) -> list[ProoflinkCheck]:
    return [validate_prooflink(prooflink, permit_dir) for prooflink in finding.prooflinks]


def finding_has_valid_prooflink(finding: Finding, permit_dir: str | Path) -> bool:
    return any(check.valid for check in validate_finding(finding, permit_dir))
