from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EnvironmentInput(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    provider: Literal["aws", "onprem", "sandbox"]
    description: str = Field(default="", max_length=2000)
    resource_scope: list[str] = Field(default_factory=list, max_length=100)


class ServiceInput(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    environment_id: UUID
    owner: str = Field(default="unassigned", max_length=160)
    criticality: Literal["low", "medium", "high", "critical"] = "medium"


class IncidentInput(StrictModel):
    environment_id: UUID
    service_id: UUID | None = None
    title: str = Field(min_length=3, max_length=255)
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    source: str = Field(default="manual", max_length=64)
    external_id: str = Field(min_length=1, max_length=255)
    evidence: dict = Field(default_factory=dict)


class IncidentTransition(StrictModel):
    status: Literal[
        "NEW",
        "INVESTIGATING",
        "AWAITING_APPROVAL",
        "REMEDIATING",
        "MONITORING_RECOVERY",
        "RESOLVED",
        "REOPENED",
        "CLOSED",
    ]
    note: str = Field(min_length=3, max_length=1000)


class IntegrationConfig(StrictModel):
    url: str = Field(default="", max_length=2048)
    region: str = Field(default="us-east-1", pattern=r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
    repository: str = Field(default="", pattern=r"^(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?$")
    query: str = Field(default="up", max_length=1024)
    username: str = Field(default="", max_length=160)


class IntegrationInput(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    environment_id: UUID
    provider: Literal["aws", "prometheus", "grafana", "github", "jenkins", "alertmanager"]
    config: IntegrationConfig
    secret_ref: str | None = Field(default=None, pattern=r"^ATLAS_SECRET_[A-Z0-9_]{1,80}$")


class PlanParameters(StrictModel):
    expected_revision: int = Field(ge=0)


class ProposalInput(StrictModel):
    action_type: Literal["sandbox.recover"] = "sandbox.recover"
    resource_id: UUID
    parameters: PlanParameters
    reason: str = Field(min_length=10, max_length=2000)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=20)
    expected_effect: str = Field(default="Sandbox resource becomes healthy", max_length=1000)
    risk: Literal["low"] = "low"
    impact: str = Field(default="Only a synthetic database sandbox resource changes", max_length=1000)
    rollback: str = Field(default="Discard and reseed the dedicated demo sandbox", max_length=1000)
    expires_in_minutes: int = Field(default=30, ge=1, le=60)


class DecisionInput(StrictModel):
    decision: Literal["APPROVE", "REJECT"]
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class Hypothesis(StrictModel):
    statement: str = Field(min_length=3, max_length=2000)
    supporting_evidence: list[str] = Field(max_length=20)
    contradicting_evidence: list[str] = Field(default_factory=list, max_length=20)


class Finding(StrictModel):
    classification: Literal["confirmed", "probable", "hypothesis", "insufficient_evidence"]
    summary: str = Field(min_length=3, max_length=3000)
    confidence: float = Field(ge=0, le=1)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=5)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    missing_data: list[str] = Field(default_factory=list, max_length=20)
    next_queries: list[str] = Field(default_factory=list, max_length=10)
    remediation: str | None = Field(default=None, max_length=2000)


class ConnectorEnroll(StrictModel):
    environment_id: UUID
    name: str = Field(min_length=2, max_length=160)
    resource: str = Field(min_length=1, max_length=255)


class ConnectorObservation(StrictModel):
    sequence: int = Field(ge=1)
    observed_at: datetime
    version: str = Field(max_length=40)
    resource: str = Field(max_length=255)
    diagnostics: dict

    @field_validator("diagnostics")
    @classmethod
    def bounded_diagnostics(cls, value):
        import json

        if len(json.dumps(value)) > 32768:
            raise ValueError("Diagnostics exceed 32 KiB")
        allowed = {
            "cpu_load",
            "memory_total_kib",
            "memory_available_kib",
            "disk_total",
            "disk_free",
            "services",
            "log_references",
            "hostname",
            "uptime_seconds",
        }
        if set(value) - allowed:
            raise ValueError("Unsupported diagnostic fields")
        return value


class ReportRequest(StrictModel):
    day: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class InvestigationInput(StrictModel):
    use_ai: bool = True
