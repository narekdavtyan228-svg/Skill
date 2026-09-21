"""Deterministic adapters for the four synthetic PermitGuard registries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
import re
from typing import Final

from core.schemas import (
    AssetIsolationRecord,
    EmployeeClearanceRecord,
    GasTestStatusRecord,
    Prooflink,
    SiteRestrictionsRecord,
)


_CALL_LOG: list[str] = []
_KNOWN_EMPLOYEE: Final = "EMP-001"
_KNOWN_ASSET: Final = "ASSET-001"
_KNOWN_ZONE: Final = "ZONE-A"
_PERMIT_PATTERN: Final = re.compile(r"^PERMIT-(\d{3})$")
_DATASET_SEED: Final = 20260920


def reset_call_log() -> None:
    _CALL_LOG.clear()


def get_call_log() -> tuple[str, ...]:
    return tuple(_CALL_LOG)


def _record(endpoint: str, queried_id: str) -> None:
    _CALL_LOG.append(f"{endpoint}:{queried_id}")


def _proof(endpoint: str, queried_id: str, quote: str) -> Prooflink:
    return Prooflink(
        source_id=f"mock://{endpoint}",
        location="row:1",
        quote=f"{queried_id}: {quote}",
    )


def employee_clearance(employee_id: str) -> EmployeeClearanceRecord:
    query = employee_id.strip() or "unknown"
    _record("employee_clearance", query)
    if query == _KNOWN_EMPLOYEE:
        return EmployeeClearanceRecord(
            queried_id=query,
            status="clear",
            cleared=True,
            valid_until=datetime(2030, 1, 1, tzinfo=timezone.utc),
            allowed_zones=["ZONE-A", "ZONE-B"],
            prooflinks=[_proof("employee_clearance", query, "clear through 2030-01-01")],
        )
    return EmployeeClearanceRecord(
        queried_id=query,
        status="unknown",
        cleared=None,
        prooflinks=[_proof("employee_clearance", query, "record not found")],
    )


def _synthetic_gas_window(permit_id: str) -> tuple[datetime, datetime] | None:
    """Reproduce the seeded fixture schedule without reading generated files."""

    match = _PERMIT_PATTERN.fullmatch(permit_id)
    if match is None:
        return None
    index = int(match.group(1))
    if not 1 <= index <= 60:
        return None

    rng = random.Random(_DATASET_SEED)
    start_minute = 0
    for _ in range(index):
        start_minute = rng.choice((15, 20, 25))
        rng.choice((4, 5, 6))
        rng.choice(("inspection", "maintenance", "valve_service"))

    day = datetime(2026, 9, 20, 6, tzinfo=timezone.utc) + timedelta(
        days=(index - 1) % 12
    )
    tested_at = day.replace(minute=start_minute) - timedelta(minutes=15)
    return tested_at, tested_at + timedelta(minutes=30)


def gas_test_status(permit_id: str) -> GasTestStatusRecord:
    query = permit_id.strip() or "unknown"
    _record("gas_test_status", query)
    gas_window = _synthetic_gas_window(query)
    if gas_window is not None:
        tested_at, valid_until = gas_window
        return GasTestStatusRecord(
            queried_id=query,
            status="clear",
            valid=True,
            tested_at=tested_at,
            valid_until=valid_until,
            prooflinks=[
                _proof(
                    "gas_test_status",
                    query,
                    f"valid until {valid_until.isoformat().replace('+00:00', 'Z')}",
                )
            ],
        )
    return GasTestStatusRecord(
        queried_id=query,
        status="unknown",
        valid=None,
        prooflinks=[_proof("gas_test_status", query, "record not found")],
    )


def asset_isolation(asset_id: str) -> AssetIsolationRecord:
    query = asset_id.strip() or "unknown"
    _record("asset_isolation", query)
    if query == _KNOWN_ASSET:
        return AssetIsolationRecord(
            queried_id=query,
            status="clear",
            isolated=True,
            isolation_id="LOTO-001",
            prooflinks=[_proof("asset_isolation", query, "LOTO-001 confirmed")],
        )
    return AssetIsolationRecord(
        queried_id=query,
        status="unknown",
        isolated=None,
        prooflinks=[_proof("asset_isolation", query, "record not found")],
    )


def site_restrictions(zone_id: str) -> SiteRestrictionsRecord:
    query = zone_id.strip() or "unknown"
    _record("site_restrictions", query)
    if query == _KNOWN_ZONE:
        return SiteRestrictionsRecord(
            queried_id=query,
            status="clear",
            work_allowed=True,
            restrictions=[],
            prooflinks=[_proof("site_restrictions", query, "no active restrictions")],
        )
    return SiteRestrictionsRecord(
        queried_id=query,
        status="unknown",
        work_allowed=None,
        restrictions=["zone is absent from the synthetic registry"],
        prooflinks=[_proof("site_restrictions", query, "record not found")],
    )
