import hashlib
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from atlasops.access import audit, scoped_get
from atlasops.models import Environment, Incident, IncidentEvent, Observation, Service, now
from atlasops.schemas import IncidentInput

INCIDENT_TRANSITIONS = {
    "NEW": {"INVESTIGATING", "CLOSED"},
    "INVESTIGATING": {"AWAITING_APPROVAL", "MONITORING_RECOVERY", "RESOLVED", "CLOSED"},
    "AWAITING_APPROVAL": {"INVESTIGATING", "REMEDIATING", "CLOSED"},
    "REMEDIATING": {"MONITORING_RECOVERY", "INVESTIGATING"},
    "MONITORING_RECOVERY": {"RESOLVED", "INVESTIGATING"},
    "RESOLVED": {"REOPENED", "CLOSED"},
    "REOPENED": {"INVESTIGATING", "CLOSED"},
    "CLOSED": {"REOPENED"},
}


def ingest(session, principal, body: IncidentInput):
    env = scoped_get(session, Environment, str(body.environment_id), principal)
    if not principal.permits_environment(env.id):
        raise HTTPException(404, "Not found")
    if body.service_id:
        service = scoped_get(session, Service, str(body.service_id), principal)
        if service.environment_id != env.id:
            raise HTTPException(422, "Service belongs to a different environment")
    fingerprint = hashlib.sha256(f"{env.id}:{body.source}:{body.external_id}".encode()).hexdigest()
    values = {
        "tenant_id": principal.tenant_id,
        "environment_id": env.id,
        "title": body.title,
        "severity": body.severity,
        "source": body.source,
        "fingerprint": fingerprint,
        "service_id": str(body.service_id) if body.service_id else None,
    }
    object_id = session.scalar(
        insert(Incident)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["tenant_id", "fingerprint"])
        .returning(Incident.id)
    )
    if not object_id:
        existing = session.scalar(
            select(Incident)
            .where(Incident.tenant_id == principal.tenant_id, Incident.fingerprint == fingerprint)
            .with_for_update()
        )
        existing.last_observed_at = now()
        if existing.status in {"CLOSED", "RESOLVED"}:
            existing.status = "REOPENED"
            event(session, existing, "reopened", "The same alert recurred")
        return existing
    incident = session.get(Incident, object_id)
    event(session, incident, "alert", "Incident ingested", {"source": body.source})
    # Store bounded, normalized evidence, not entire untrusted request bodies or raw logs.
    safe_keys = {
        "metric",
        "value",
        "unit",
        "route",
        "status_code",
        "trace_id",
        "span_id",
        "deployment_revision",
        "reference",
        "synthetic",
        "resource",
    }
    evidence = {
        k: v for k, v in body.evidence.items() if k in safe_keys and isinstance(v, (str, int, float, bool))
    }
    if evidence:
        session.add(
            Observation(
                tenant_id=principal.tenant_id,
                environment_id=env.id,
                source=body.source,
                resource=str(evidence.get("resource", body.service_id or env.id)),
                data=evidence,
                quality="synthetic" if evidence.get("synthetic") else "partial",
            )
        )
    audit(session, principal, "incident.ingested", incident)
    return incident


def event(session, incident, kind: str, message: str, data=None):
    session.add(
        IncidentEvent(
            tenant_id=incident.tenant_id,
            environment_id=incident.environment_id,
            incident_id=incident.id,
            kind=kind,
            message=message,
            data=data or {},
        )
    )


def transition_incident(session, principal, incident, target, note):
    if target not in INCIDENT_TRANSITIONS.get(incident.status, set()):
        raise HTTPException(409, "Invalid incident state transition")
    if target == "RESOLVED":
        # Human resolution remains explicit; no LLM or successful adapter call auto-resolves an incident.
        principal.require("operate")
    incident.status = target
    event(session, incident, "status", note, {"status": target})
    audit(session, principal, "incident.transition", incident, {"status": target})


def incident_evidence(session, incident):
    window_start = incident.first_observed_at - timedelta(minutes=30)
    rows = session.scalars(
        select(Observation)
        .where(
            Observation.tenant_id == incident.tenant_id,
            Observation.environment_id == incident.environment_id,
            Observation.observed_at >= window_start,
            Observation.observed_at <= now(),
        )
        .order_by(Observation.observed_at.desc())
        .limit(50)
    ).all()
    return [
        {
            "id": row.id,
            "source": row.source,
            "observed_at": row.observed_at.isoformat(),
            "resource": row.resource,
            "quality": row.quality,
            "data": row.data,
        }
        for row in rows
    ]
