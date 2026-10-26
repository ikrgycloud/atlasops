"""Explicit read-only investigation tool registry, separate from any execution service."""

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select

from atlasops.access import audit, scoped_get
from atlasops.models import Incident, Observation, now
from atlasops.schemas import StrictModel


class EvidenceQuery(StrictModel):
    tool: Literal["evidence.read"] = "evidence.read"
    incident_id: UUID
    start: datetime
    end: datetime
    limit: int = Field(default=50, ge=1, le=50)

    @model_validator(mode="after")
    def bounded_window(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Timezone-aware query window required")
        if not timedelta(0) < self.end - self.start <= timedelta(hours=2) or self.end > now() + timedelta(
            seconds=30
        ):
            raise ValueError("Diagnostic window must be positive, at most two hours, and not in the future")
        return self


def run_diagnostic(session, principal, query: EvidenceQuery):
    principal.require("operate")
    incident = scoped_get(session, Incident, str(query.incident_id), principal)
    if query.start < incident.first_observed_at - timedelta(hours=1):
        raise HTTPException(422, "Query starts outside the incident investigation window")
    records = session.scalars(
        select(Observation)
        .where(
            Observation.tenant_id == principal.tenant_id,
            Observation.environment_id == incident.environment_id,
            Observation.observed_at >= query.start,
            Observation.observed_at <= query.end,
        )
        .order_by(Observation.observed_at.desc())
        .limit(query.limit)
    ).all()
    audit(
        session,
        principal,
        "diagnostic.evidence_read",
        incident,
        {"limit": query.limit, "start": query.start.isoformat(), "end": query.end.isoformat()},
    )
    return [
        {
            "id": r.id,
            "source": r.source,
            "resource": r.resource,
            "observed_at": r.observed_at.isoformat(),
            "quality": r.quality,
            "data": r.data,
        }
        for r in records
    ]
