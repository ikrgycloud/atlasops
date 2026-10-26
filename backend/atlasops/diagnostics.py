"""Audited, scoped database diagnostics. No commands, provider mutation, arbitrary URLs or raw SQL inputs."""

from datetime import datetime, timedelta
from types import MappingProxyType
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy import or_, text

from atlasops.access import audit, scoped_get, scoped_query
from atlasops.ai_schemas import DiagnosticName
from atlasops.auth import resolve_principal
from atlasops.config import settings
from atlasops.models import Deployment, Environment, Incident, Observation, now
from atlasops.privacy import redact_evidence
from atlasops.schemas import StrictModel


class EvidenceQuery(StrictModel):
    tool: DiagnosticName = "evidence.read"
    incident_id: UUID
    start: datetime
    end: datetime
    resource: str | None = Field(default=None, min_length=1, max_length=255)
    limit: int = Field(default=50, ge=1, le=50)

    @model_validator(mode="after")
    def bounded_window(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Timezone-aware query window required")
        maximum = timedelta(seconds=settings().ai_max_query_window_seconds)
        if not timedelta(0) < self.end - self.start <= maximum or self.end > now() + timedelta(seconds=30):
            raise ValueError("Diagnostic query window exceeds the configured time boundary")
        return self


def _incident(session, principal, incident, environment, query):
    return [
        {
            "id": "incident:" + incident.id,
            "kind": "incident",
            "source": incident.source,
            "resource": str(incident.service_id or incident.environment_id),
            "observed_at": incident.first_observed_at.isoformat(),
            "quality": "context",
            "data": redact_evidence(
                {
                    "title": incident.title,
                    "severity": incident.severity,
                    "status": incident.status,
                    "service_id": incident.service_id,
                    "last_observed_at": incident.last_observed_at.isoformat(),
                }
            ),
        }
    ]


def _observations(session, principal, incident, environment, query):
    stmt = scoped_query(Observation, principal).where(
        Observation.environment_id == incident.environment_id,
        Observation.observed_at >= query.start,
        Observation.observed_at <= query.end,
    )
    if environment.resource_scope:
        stmt = stmt.where(Observation.resource.in_(environment.resource_scope))
    if query.resource:
        stmt = stmt.where(Observation.resource == query.resource)
    if query.tool == "metrics.read":
        stmt = stmt.where(Observation.data["metric"].as_string().is_not(None))
    elif query.tool == "logs.references":
        stmt = stmt.where(
            or_(
                Observation.data["reference"].as_string().is_not(None),
                Observation.data["log_references"].as_string().is_not(None),
            )
        )
    elif query.tool == "traces.references":
        stmt = stmt.where(Observation.data["trace_id"].as_string().is_not(None))
    rows = session.scalars(stmt.order_by(Observation.observed_at.desc()).limit(query.limit)).all()
    records = []
    for row in rows:
        data = row.data
        kind = "metric" if data.get("metric") else "observation"
        if query.tool in {"logs.references", "traces.references"}:
            keys = (
                {"reference", "log_references", "route", "trace_id", "span_id", "deployment_revision"}
                if query.tool == "logs.references"
                else {"trace_id", "span_id", "route", "deployment_revision"}
            )
            data = {k: v for k, v in data.items() if k in keys}
            kind = "log_reference" if query.tool == "logs.references" else "trace_reference"
        safe_data = redact_evidence(data)
        records.append(
            {
                "id": row.id,
                "kind": kind,
                "source": row.source,
                "resource": row.resource,
                "observed_at": row.observed_at.isoformat(),
                "quality": row.quality,
                "data": safe_data,
                "data_limited": safe_data != data,
            }
        )
    return records


def _deployments(session, principal, incident, environment, query):
    # Deployment records have environment scope, not a verified per-resource target.
    if query.resource:
        return []
    rows = session.scalars(
        scoped_query(Deployment, principal)
        .where(
            Deployment.environment_id == incident.environment_id,
            Deployment.observed_at >= query.start,
            Deployment.observed_at <= query.end,
        )
        .order_by(Deployment.observed_at.desc())
        .limit(query.limit)
    ).all()
    return [
        {
            "id": "deployment:" + row.id,
            "kind": "deployment",
            "source": row.provider,
            "resource": row.environment_id,
            "observed_at": row.observed_at.isoformat(),
            "quality": "metadata",
            "data": redact_evidence(
                {
                    "revision": row.revision,
                    "branch": row.branch,
                    "workflow": row.workflow,
                    "status": row.status,
                    "repository": row.repository,
                    "reference": row.run_url,
                }
            ),
        }
        for row in rows
    ]


# Immutable registry: the planner cannot register or name arbitrary callables.
REGISTRY = MappingProxyType(
    {
        "incident.read": (_incident, "Incident context and timestamps"),
        "evidence.read": (
            _observations,
            "Stored authorized observations, including ingested metric/log/trace references",
        ),
        "metrics.read": (
            _observations,
            "Stored metric observations only; no model-supplied PromQL or external query",
        ),
        "deployments.read": (_deployments, "Environment-level deployment metadata in the selected window"),
        "logs.references": (_observations, "Authorized stored log references; no raw external log fetching"),
        "traces.references": (
            _observations,
            "Authorized stored trace/span IDs; no external span payload fetching",
        ),
    }
)


def registered_tools():
    return [{"name": name, "description": entry[1], "read_only": True} for name, entry in REGISTRY.items()]


def run_diagnostic(session, principal, query: EvidenceQuery):
    principal = resolve_principal(session, principal.user_id, principal.tenant_id)
    principal.require("operate")
    incident = scoped_get(session, Incident, str(query.incident_id), principal)
    environment = scoped_get(session, Environment, incident.environment_id, principal)
    session.refresh(environment)
    if query.start < incident.first_observed_at - timedelta(
        hours=1
    ) or query.end > incident.last_observed_at + timedelta(hours=1):
        raise HTTPException(422, "Diagnostic query is outside the incident investigation window")
    if query.resource and environment.resource_scope and query.resource not in environment.resource_scope:
        raise HTTPException(403, "Diagnostic resource is outside environment scope")
    # An idle/slow database cannot give a model an unbounded read operation.
    session.execute(text("SELECT set_config('statement_timeout', '2000', true)"))
    handler, _ = REGISTRY[query.tool]
    records = handler(session, principal, incident, environment, query)
    audit(
        session,
        principal,
        "diagnostic." + query.tool,
        incident,
        {
            "limit": query.limit,
            "resource": query.resource,
            "start": query.start.isoformat(),
            "end": query.end.isoformat(),
            "returned": len(records),
        },
    )
    return records
