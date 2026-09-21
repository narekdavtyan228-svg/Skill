"""Strict Pydantic contracts shared by all PermitGuard layers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Classification = Literal["confirmed", "contested", "unknown", "insufficient_evidence"]
EvidenceStatus = Literal["confirmed", "contested", "unknown", "insufficient_evidence"]
Severity = Literal["P1", "P2", "P3"]
Verdict = Literal["approve", "approve_with_conditions", "block_and_escalate"]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class Prooflink(StrictModel):
    source_id: str = Field(min_length=1)
    location: str = Field(pattern=r"^(page|row):[1-9][0-9]*$")
    quote: str = Field(min_length=1)

    @field_validator("source_id", "quote")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prooflink text must not be blank")
        return value


class Validation(StrictModel):
    rules_passed: list[str] = Field(default_factory=list)
    rules_failed: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)

    @field_validator("rules_passed", "rules_failed", "unknowns")
    @classmethod
    def reject_blank_items(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError("validation entries must not be blank")
        return values


class Finding(StrictModel):
    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    severity: Severity
    classification: Classification
    claim: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    prooflinks: list[Prooflink] = Field(default_factory=list)
    validation: Validation
    requires_human_review: Literal[True]
    required_human_decision: str = Field(min_length=1)

    @field_validator("finding_id", "rule_id", "claim", "required_human_decision")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("finding text must not be blank")
        return value

    @model_validator(mode="after")
    def confirmed_requires_proof(self) -> "Finding":
        if self.classification == "confirmed" and not self.prooflinks:
            raise ValueError("confirmed findings require at least one prooflink")
        return self


class PermitResult(StrictModel):
    task_id: Literal["permitguard"] = "permitguard"
    run_id: str = Field(min_length=1)
    status: Literal["completed"] = "completed"
    verdict: Verdict
    findings: list[Finding] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    audit_log: list[str] = Field(default_factory=list)
    requires_human_review: Literal[True] = True
    required_human_decision: str = Field(min_length=1)

    @field_validator("run_id", "required_human_decision")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("result text must not be blank")
        return value

    @field_validator("unknowns", "audit_log")
    @classmethod
    def reject_blank_items(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError("result entries must not be blank")
        return values

    @model_validator(mode="after")
    def enforce_fail_closed(self) -> "PermitResult":
        if self.unknowns and self.verdict != "block_and_escalate":
            raise ValueError("unknowns require block_and_escalate")
        return self


ValueT = TypeVar("ValueT")


class EvidenceValue(StrictModel, Generic[ValueT]):
    value: ValueT | None
    status: EvidenceStatus
    prooflinks: list[Prooflink] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_matches_value(self) -> "EvidenceValue[ValueT]":
        if self.value is not None and not self.prooflinks:
            raise ValueError("a present extracted value requires a prooflink")
        if self.value is None and self.status in {"confirmed", "contested"}:
            raise ValueError("a missing value must be unknown or insufficient_evidence")
        if self.value is not None and self.status in {"unknown", "insufficient_evidence"}:
            raise ValueError("an unknown value must be represented as None")
        return self


class ExtractedPermit(StrictModel):
    """Layer B output. Every usable value carries its own source evidence."""

    permit_id: EvidenceValue[str]
    employee_id: EvidenceValue[str]
    asset_id: EvidenceValue[str]
    zone_id: EvidenceValue[str]
    work_start: EvidenceValue[datetime]
    work_end: EvidenceValue[datetime]
    gas_tested_at: EvidenceValue[datetime]
    gas_valid_minutes: EvidenceValue[int]
    responsible_signature: EvidenceValue[bool]
    isolation_id: EvidenceValue[str]
    concurrent_work_zones: EvidenceValue[list[str]]
    shift_start: EvidenceValue[datetime]
    shift_end: EvidenceValue[datetime]
    required_documents_present: EvidenceValue[bool]
    contradictions: list[str] = Field(default_factory=list)

    @field_validator("contradictions")
    @classmethod
    def reject_blank_contradictions(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError("contradictions must not be blank")
        return values

    def missing_fields(self) -> list[str]:
        return [
            name
            for name in type(self).model_fields
            if name != "contradictions"
            and isinstance(getattr(self, name), EvidenceValue)
            and getattr(self, name).value is None
        ]


RegistryStatus = Literal["clear", "blocked", "unknown"]


class RegistryRecord(StrictModel):
    queried_id: str = Field(min_length=1)
    status: RegistryStatus
    prooflinks: list[Prooflink] = Field(min_length=1)


class EmployeeClearanceRecord(RegistryRecord):
    cleared: bool | None
    valid_until: datetime | None = None
    allowed_zones: list[str] = Field(default_factory=list)


class GasTestStatusRecord(RegistryRecord):
    valid: bool | None
    tested_at: datetime | None = None
    valid_until: datetime | None = None


class AssetIsolationRecord(RegistryRecord):
    isolated: bool | None
    isolation_id: str | None = None


class SiteRestrictionsRecord(RegistryRecord):
    work_allowed: bool | None
    restrictions: list[str] = Field(default_factory=list)


class RegistrySnapshot(StrictModel):
    employee_clearance: EmployeeClearanceRecord
    gas_test_status: GasTestStatusRecord
    asset_isolation: AssetIsolationRecord
    site_restrictions: SiteRestrictionsRecord
    queried_endpoints: tuple[
        Literal["employee_clearance"],
        Literal["gas_test_status"],
        Literal["asset_isolation"],
        Literal["site_restrictions"],
    ]


def unknown_evidence() -> EvidenceValue[Any]:
    return EvidenceValue[Any](value=None, status="insufficient_evidence", prooflinks=[])
