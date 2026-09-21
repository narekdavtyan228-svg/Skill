"""Offline extraction of PermitGuard PDF, JSON and CSV bundles."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

import pymupdf as fitz

from core.schemas import EvidenceValue, ExtractedPermit, Prooflink


ValueT = TypeVar("ValueT")
_LABEL = re.compile(r"^([A-Za-z ]+):\s*(.*?)\s*$")


def _unknown() -> EvidenceValue[Any]:
    return EvidenceValue[Any](value=None, status="insufficient_evidence", prooflinks=[])


def _known(value: ValueT, source_id: str, location: str, quote: str) -> EvidenceValue[ValueT]:
    return EvidenceValue[ValueT](
        value=value,
        status="confirmed",
        prooflinks=[Prooflink(source_id=source_id, location=location, quote=quote)],
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return parsed


def _parse_bool(value: str) -> bool:
    normalized = value.strip().upper()
    if normalized == "YES":
        return True
    if normalized == "NO":
        return False
    raise ValueError("boolean must be YES or NO")


def _parse_zones(value: str) -> list[str]:
    if value.strip().upper() == "NONE":
        return []
    zones = [item.strip() for item in value.split(",") if item.strip()]
    if not zones:
        raise ValueError("zone list is empty")
    return zones


def _read_pdf_fields(path: Path, contradictions: list[str]) -> dict[str, tuple[str, Prooflink]]:
    matches: dict[str, list[tuple[str, Prooflink]]] = {}
    try:
        with fitz.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                for raw_line in page.get_text().splitlines():
                    line = raw_line.strip()
                    match = _LABEL.fullmatch(line)
                    if match is None:
                        continue
                    label = match.group(1).strip().casefold()
                    proof = Prooflink(
                        source_id=path.name,
                        location=f"page:{page_number}",
                        quote=line,
                    )
                    matches.setdefault(label, []).append((match.group(2).strip(), proof))
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        contradictions.append(f"Unreadable PDF {path.name}: {exc}")
        return {}

    fields: dict[str, tuple[str, Prooflink]] = {}
    for label, values in matches.items():
        if len(values) == 1:
            fields[label] = values[0]
        else:
            contradictions.append(f"Ambiguous PDF field: {label}")
    return fields


def _pdf_value(
    fields: dict[str, tuple[str, Prooflink]],
    label: str,
    parser: Callable[[str], ValueT],
    contradictions: list[str],
) -> EvidenceValue[ValueT]:
    item = fields.get(label.casefold())
    if item is None:
        return _unknown()
    raw, proof = item
    try:
        return EvidenceValue[ValueT](value=parser(raw), status="confirmed", prooflinks=[proof])
    except (TypeError, ValueError, OverflowError) as exc:
        contradictions.append(f"Invalid PDF field {label}: {exc}")
        return _unknown()


def _json_line(path: Path, key: str) -> tuple[int, str] | None:
    pattern = re.compile(rf'^\s*"{re.escape(key)}"\s*:')
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    found = [(number, line.strip()) for number, line in enumerate(lines, start=1) if pattern.search(line)]
    return found[0] if len(found) == 1 else None


def _read_employee(
    path: Path | None,
    pdf_employee: EvidenceValue[str],
    permit_id: EvidenceValue[str],
    contradictions: list[str],
) -> EvidenceValue[str]:
    if path is None:
        return _unknown()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        employee = payload.get("employee_id")
        row = _json_line(path, "employee_id")
        if not isinstance(employee, str) or not employee.strip() or row is None:
            return _unknown()
        if permit_id.value is not None and payload.get("permit_id") != permit_id.value:
            contradictions.append("Employee card permit_id conflicts with permit PDF")
            return _unknown()
        if pdf_employee.value is not None and employee != pdf_employee.value:
            contradictions.append("Employee ID conflicts between card and permit PDF")
            return _unknown()
        return _known(employee, path.name, f"row:{row[0]}", row[1])
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        contradictions.append(f"Unreadable employee card: {exc}")
        return _unknown()


def _read_csv_rows(path: Path, contradictions: list[str]) -> list[tuple[int, dict[str, str], str]]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error) as exc:
        contradictions.append(f"Unreadable CSV {path.name}: {exc}")
        return []
    if len(lines) != len(rows) + 1:
        contradictions.append(f"Multiline or malformed CSV rows in {path.name}")
        return []
    return [(index, row, lines[index - 1]) for index, row in enumerate(rows, start=2)]


def _select_csv_row(
    path: Path | None,
    permit_id: EvidenceValue[str],
    contradictions: list[str],
) -> tuple[Path, int, dict[str, str], str] | None:
    if path is None or permit_id.value is None:
        return None
    matching = [row for row in _read_csv_rows(path, contradictions) if row[1].get("permit_id") == permit_id.value]
    if len(matching) != 1:
        if len(matching) > 1:
            contradictions.append(f"Ambiguous rows for {permit_id.value} in {path.name}")
        elif path.is_file():
            contradictions.append(f"No row for {permit_id.value} in {path.name}")
        return None
    row_number, row, quote = matching[0]
    return path, row_number, row, quote


def _csv_value(
    selected: tuple[Path, int, dict[str, str], str] | None,
    column: str,
    parser: Callable[[str], ValueT],
    contradictions: list[str],
) -> EvidenceValue[ValueT]:
    if selected is None:
        return _unknown()
    path, row_number, row, quote = selected
    raw = row.get(column)
    if raw is None or not raw.strip():
        return _unknown()
    try:
        return _known(parser(raw), path.name, f"row:{row_number}", quote)
    except (TypeError, ValueError, OverflowError) as exc:
        contradictions.append(f"Invalid {column} in {path.name}: {exc}")
        return _unknown()


def _single_file(root: Path, pattern: str, contradictions: list[str]) -> Path | None:
    matches = sorted(path for path in root.glob(pattern) if path.is_file())
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        contradictions.append(f"Ambiguous document pattern: {pattern}")
    else:
        contradictions.append(f"Missing document: {pattern}")
    return None


def extract_permit(permit_dir: str | Path) -> ExtractedPermit:
    """Extract a permit bundle without network calls or inferred values."""

    root = Path(permit_dir)
    if not root.is_dir():
        raise ValueError(f"permit bundle is not a directory: {root}")

    contradictions: list[str] = []
    pdf_path = _single_file(root, "permit_*.pdf", contradictions)
    employee_path = _single_file(root, "employee_card.json", contradictions)
    gas_path = _single_file(root, "gas_log.csv", contradictions)
    isolation_path = _single_file(root, "isolations.csv", contradictions)

    fields = _read_pdf_fields(pdf_path, contradictions) if pdf_path is not None else {}
    permit_id = _pdf_value(fields, "permit id", str, contradictions)
    pdf_employee = _pdf_value(fields, "employee id", str, contradictions)
    asset_id = _pdf_value(fields, "asset id", str, contradictions)
    zone_id = _pdf_value(fields, "zone id", str, contradictions)
    work_start = _pdf_value(fields, "work start", _parse_datetime, contradictions)
    work_end = _pdf_value(fields, "work end", _parse_datetime, contradictions)
    shift_start = _pdf_value(fields, "shift start", _parse_datetime, contradictions)
    shift_end = _pdf_value(fields, "shift end", _parse_datetime, contradictions)
    signature = _pdf_value(fields, "responsible signature", _parse_bool, contradictions)
    concurrent = _pdf_value(fields, "concurrent work zones", _parse_zones, contradictions)
    declared_documents = _pdf_value(fields, "required documents present", _parse_bool, contradictions)

    employee_id = _read_employee(employee_path, pdf_employee, permit_id, contradictions)
    gas_row = _select_csv_row(gas_path, permit_id, contradictions)
    gas_tested_at = _csv_value(gas_row, "tested_at", _parse_datetime, contradictions)
    gas_valid_minutes = _csv_value(gas_row, "valid_minutes", int, contradictions)
    isolation_row = _select_csv_row(isolation_path, permit_id, contradictions)

    isolation_id: EvidenceValue[str]
    if isolation_row is None:
        isolation_id = _unknown()
    else:
        path, row_number, row, quote = isolation_row
        if row.get("asset_id") != asset_id.value:
            contradictions.append("Isolation asset_id conflicts with permit PDF")
            isolation_id = _unknown()
        elif row.get("status", "").strip().upper() != "CONFIRMED":
            isolation_id = EvidenceValue[str](
                value=None,
                status="insufficient_evidence",
                prooflinks=[Prooflink(source_id=path.name, location=f"row:{row_number}", quote=quote)],
            )
        else:
            isolation_id = _csv_value(isolation_row, "isolation_id", str, contradictions)

    all_present = all(path is not None for path in (pdf_path, employee_path, gas_path, isolation_path))
    required_documents = declared_documents if all_present else _unknown()
    if not all_present and declared_documents.value is True:
        contradictions.append("Permit declares all documents present but the bundle is incomplete")

    return ExtractedPermit(
        permit_id=permit_id,
        employee_id=employee_id,
        asset_id=asset_id,
        zone_id=zone_id,
        work_start=work_start,
        work_end=work_end,
        gas_tested_at=gas_tested_at,
        gas_valid_minutes=gas_valid_minutes,
        responsible_signature=signature,
        isolation_id=isolation_id,
        concurrent_work_zones=concurrent,
        shift_start=shift_start,
        shift_end=shift_end,
        required_documents_present=required_documents,
        contradictions=list(dict.fromkeys(contradictions)),
    )
