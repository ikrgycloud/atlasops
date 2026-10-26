import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlasops.access import audit, scoped_get, scoped_query
from atlasops.actions import decide, propose
from atlasops.adapters.contracts import AdapterError
from atlasops.auth import Principal, current_user
from atlasops.db import get_session
from atlasops.incidents import incident_evidence, ingest, transition_incident
from atlasops.integrations import CAPABILITIES, probe, validate_integration
from atlasops.jobs import enqueue
from atlasops.models import (
    ActionExecution,
    ActionProposal,
    Approval,
    AuditEvent,
    BackgroundJob,
    Connector,
    Deployment,
    Environment,
    Incident,
    IncidentEvent,
    Integration,
    Investigation,
    NotificationDelivery,
    Observation,
    Report,
    SandboxResource,
    now,
    public_record,
)
from atlasops.reporting import coverage, scope_key
from atlasops.schemas import (
    ConnectorEnroll,
    ConnectorObservation,
    DecisionInput,
    IncidentInput,
    IncidentTransition,
    IntegrationInput,
    InvestigationInput,
    ProposalInput,
    ReportRequest,
)

router = APIRouter(prefix="/api/v1")


def paginate(session, model, principal, limit=25, offset=0, query=None):
    query = query if query is not None else scoped_query(model, principal)
    count = session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = session.scalars(query.order_by(model.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [public_record(r) for r in rows], "total": count, "limit": limit, "offset": offset}


@router.get("/summary")
def summary(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    def count(model, *conditions):
        query = scoped_query(model, p).where(*conditions)
        if model == Environment and "*" not in p.environment_ids:
            query = query.where(Environment.id.in_(p.environment_ids))
        return session.scalar(select(func.count()).select_from(query.subquery()))

    recent = session.scalars(
        scoped_query(Incident, p).where(Incident.created_at >= now() - timedelta(days=7))
    ).all()
    from collections import Counter

    daily = Counter(i.created_at.date().isoformat() for i in recent)
    return {
        "environments": count(Environment),
        "active_incidents": count(Incident, Incident.status.not_in(["RESOLVED", "CLOSED"])),
        "pending_approvals": count(ActionProposal, ActionProposal.state == "AWAITING_APPROVAL"),
        "verified_actions": count(ActionExecution, ActionExecution.status == "SUCCEEDED"),
        "coverage": coverage(session, p, now() - timedelta(hours=24), now()),
        "incident_series": [
            {
                "day": (now() - timedelta(days=d)).date().isoformat(),
                "incidents": daily.get((now() - timedelta(days=d)).date().isoformat(), 0),
            }
            for d in range(6, -1, -1)
        ],
    }


@router.get("/incidents")
def incidents(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    severity: str | None = None,
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    query = scoped_query(Incident, p)
    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)
    return paginate(session, Incident, p, limit, offset, query)


@router.post("/incidents", status_code=201)
def create_incident(
    body: IncidentInput, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("operate")
    row = ingest(session, p, body)
    session.commit()
    return public_record(row)


@router.get("/incidents/{incident_id}")
def incident_detail(
    incident_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    row = scoped_get(session, Incident, str(incident_id), p)
    result = public_record(row)
    result["evidence"] = incident_evidence(session, row)
    return result


@router.post("/incidents/{incident_id}/status")
def incident_status(
    incident_id: UUID,
    body: IncidentTransition,
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    p.require("operate")
    row = scoped_get(session, Incident, str(incident_id), p, for_update=True)
    transition_incident(session, p, row, body.status, body.note)
    session.commit()
    return public_record(row)


@router.get("/incidents/{incident_id}/events")
def incident_events(
    incident_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    scoped_get(session, Incident, str(incident_id), p)
    return paginate(
        session,
        IncidentEvent,
        p,
        limit=100,
        query=scoped_query(IncidentEvent, p).where(IncidentEvent.incident_id == str(incident_id)),
    )


@router.post("/incidents/{incident_id}/investigations", status_code=202)
def create_investigation(
    incident_id: UUID,
    body: InvestigationInput | None = None,
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    p.require("operate")
    incident = scoped_get(session, Incident, str(incident_id), p)
    row = Investigation(
        tenant_id=p.tenant_id, environment_id=incident.environment_id, incident_id=incident.id
    )
    session.add(row)
    session.flush()
    job_id = enqueue(
        session,
        p,
        "investigate",
        {"investigation_id": row.id, "use_ai": body.use_ai if body else True},
        f"investigation:{row.id}",
    )
    audit(session, p, "investigation.requested", row)
    session.commit()
    return {"id": row.id, "job_id": job_id, "status": "PENDING"}


@router.get("/incidents/{incident_id}/investigations")
def investigations(
    incident_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    scoped_get(session, Incident, str(incident_id), p)
    return paginate(
        session,
        Investigation,
        p,
        query=scoped_query(Investigation, p).where(Investigation.incident_id == str(incident_id)),
    )


@router.post("/incidents/{incident_id}/proposals", status_code=201)
def create_proposal(
    incident_id: UUID,
    body: ProposalInput,
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    incident = scoped_get(session, Incident, str(incident_id), p, for_update=True)
    row = propose(session, p, incident, body)
    session.commit()
    return public_record(row)


@router.get("/action-proposals")
def proposals(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    return paginate(session, ActionProposal, p, limit, offset)


@router.get("/action-proposals/{proposal_id}")
def proposal_detail(
    proposal_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    return public_record(scoped_get(session, ActionProposal, str(proposal_id), p))


@router.get("/approvals")
def approvals(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    result = paginate(session, Approval, p, limit, offset)
    for item in result["items"]:
        item["proposal"] = public_record(scoped_get(session, ActionProposal, item["proposal_id"], p))
    return result


@router.post("/approvals/{approval_id}/decision")
def approval_decision(
    approval_id: UUID,
    body: DecisionInput,
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    row = decide(session, p, str(approval_id), body)
    session.commit()
    return public_record(row)


@router.post("/action-proposals/{proposal_id}/execute", status_code=202)
def dispatch_execution(
    proposal_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("execute")
    proposal = scoped_get(session, ActionProposal, str(proposal_id), p)
    if proposal.state != "APPROVED":
        raise HTTPException(409, "Explicit approval is required before execution")
    job_id = enqueue(session, p, "execute", {"proposal_id": proposal.id}, f"execution:{proposal.id}")
    session.commit()
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_detail(job_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    job = scoped_get(session, BackgroundJob, str(job_id), p)
    if job.payload.get("actor_id") != p.user_id:
        p.require("configure")
        if "*" not in p.environment_ids:
            raise HTTPException(404, "Not found")
    return {k: v for k, v in public_record(job).items() if k != "payload"}


@router.get("/deployments")
def deployments(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    return paginate(session, Deployment, p, limit, offset)


@router.get("/deployments/{deployment_id}")
def deployment_detail(
    deployment_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    return public_record(scoped_get(session, Deployment, str(deployment_id), p))


def report_query(p):
    query = scoped_query(Report, p)
    if "*" not in p.environment_ids:
        query = query.where(Report.scope_key == scope_key(p))
    return query


@router.get("/reports")
def reports(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    return paginate(session, Report, p, limit, offset, report_query(p))


@router.get("/reports/daily")
def latest_report(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    row = session.scalar(report_query(p).order_by(Report.created_at.desc()).limit(1))
    return public_record(row) if row else None


@router.get("/reports/{report_id}")
def report_detail(
    report_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    row = session.scalar(report_query(p).where(Report.id == str(report_id)))
    if not row:
        raise HTTPException(404, "Not found")
    result = public_record(row)
    result["deliveries"] = [
        public_record(d)
        for d in session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.tenant_id == p.tenant_id, NotificationDelivery.report_id == row.id
            )
        )
    ]
    return result


@router.post("/reports/generate", status_code=202)
def create_report(
    body: ReportRequest, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("report")
    from atlasops.reporting import report_window

    try:
        start, _ = report_window(body.day)
    except ValueError:
        raise HTTPException(422, "Invalid report date")
    job_id = enqueue(session, p, "report", {"day": body.day}, f"manual-report:{start.date()}:{scope_key(p)}")
    session.commit()
    return {"job_id": job_id}


@router.get("/integrations")
def integrations(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    result = paginate(session, Integration, p, limit=100)
    for item in result["items"]:
        item["capabilities"] = CAPABILITIES[item["provider"]]
        item["credential_configured"] = bool(item.pop("secret_ref"))
    return result


@router.post("/integrations", status_code=201)
def register_integration(
    body: IntegrationInput, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("configure")
    env = scoped_get(session, Environment, str(body.environment_id), p)
    if not p.permits_environment(env.id):
        raise HTTPException(404, "Not found")
    try:
        validate_integration(body.provider, body.config.model_dump())
    except AdapterError as error:
        raise HTTPException(422, error.code)
    row = Integration(tenant_id=p.tenant_id, **body.model_dump(mode="json"))
    session.add(row)
    session.flush()
    audit(session, p, "integration.registered", row)
    session.commit()
    result = public_record(row)
    result["credential_configured"] = bool(result.pop("secret_ref"))
    return result


@router.post("/integrations/{integration_id}/test")
def test_integration(
    integration_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("configure")
    row = scoped_get(session, Integration, str(integration_id), p)
    environment = scoped_get(session, Environment, row.environment_id, p)
    result = probe(session, row, environment)
    audit(session, p, "integration.probed", row, result)
    session.commit()
    return result


@router.post("/integrations/webhooks/{provider}", status_code=202)
async def webhook(
    provider: str, request: Request, integration_id: UUID, session: Session = Depends(get_session)
):
    from atlasops.webhooks import receive

    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(413, "Webhook body exceeds 1 MiB")
    try:
        result = receive(session, provider, str(integration_id), request.headers, body)
    except AdapterError as error:
        raise HTTPException(503, error.code)
    session.commit()
    return result


@router.get("/audit-events")
def audit_events(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p: Principal = Depends(current_user),
    session: Session = Depends(get_session),
):
    p.require("audit")
    return paginate(session, AuditEvent, p, limit, offset)


@router.get("/sandbox/resources")
def sandbox_resources(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    return paginate(session, SandboxResource, p)


@router.post("/sandbox/scenario", status_code=201)
def sandbox_scenario(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    p.require("operate")
    resource = session.scalar(
        scoped_query(SandboxResource, p)
        .where(SandboxResource.healthy.is_(False))
        .order_by(SandboxResource.created_at.desc())
    )
    if not resource:
        raise HTTPException(409, "Run the development seed first")
    incident = ingest(
        session,
        p,
        IncidentInput(
            environment_id=resource.environment_id,
            title="Sample API error rate exceeds threshold",
            severity="high",
            source="sandbox-synthetic",
            external_id=f"sample-api:{resource.id}:{resource.revision}",
            evidence={
                "metric": "http_error_ratio",
                "value": 0.25 if not resource.healthy else 0.0,
                "unit": "ratio",
                "route": "/api/orders",
                "status_code": 503,
                "resource": resource.id,
                "synthetic": True,
            },
        ),
    )
    session.commit()
    return public_record(incident)


@router.get("/connectors")
def connectors(p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    p.require("configure")
    result = paginate(session, Connector, p)
    for item in result["items"]:
        item.pop("token_hash")
        item["connected"] = bool(
            item["last_seen_at"] and item["last_seen_at"] > now() - timedelta(seconds=120)
        )
    return result


@router.post("/connectors", status_code=201)
def enroll_connector(
    body: ConnectorEnroll, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("configure")
    env = scoped_get(session, Environment, str(body.environment_id), p)
    if not p.permits_environment(env.id) or env.provider != "onprem":
        raise HTTPException(403, "Connector requires an authorized on-premises environment")
    if env.resource_scope and body.resource not in env.resource_scope:
        raise HTTPException(403, "Connector resource outside environment scope")
    token = secrets.token_urlsafe(48)
    row = Connector(
        tenant_id=p.tenant_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        **body.model_dump(mode="json"),
    )
    session.add(row)
    session.flush()
    audit(session, p, "connector.enrolled", row)
    session.commit()
    return {
        "id": row.id,
        "enrollment_token": token,
        "notice": "One-time credential; store securely. Not retrievable.",
    }


@router.post("/connectors/{connector_id}/revoke")
def revoke_connector(
    connector_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("configure")
    row = scoped_get(session, Connector, str(connector_id), p, for_update=True)
    row.revoked = True
    audit(session, p, "connector.revoked", row)
    session.commit()
    return {"status": "revoked"}


@router.post("/connectors/{connector_id}/rotate")
def rotate_connector(
    connector_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    p.require("configure")
    row = scoped_get(session, Connector, str(connector_id), p, for_update=True)
    token = secrets.token_urlsafe(48)
    row.token_hash, row.last_sequence, row.revoked = hashlib.sha256(token.encode()).hexdigest(), 0, False
    audit(session, p, "connector.rotated", row)
    session.commit()
    return {"id": row.id, "enrollment_token": token}


@router.post("/connectors/observations", status_code=202)
def connector_observation(
    body: ConnectorObservation,
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid connector credential")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    connector = session.scalar(
        select(Connector)
        .where(Connector.token_hash == digest, Connector.revoked.is_(False))
        .with_for_update()
    )
    if not connector:
        raise HTTPException(401, "Invalid connector credential")
    if body.observed_at.tzinfo is None or abs((now() - body.observed_at).total_seconds()) > 120:
        raise HTTPException(409, "Observation expired or timestamp invalid")
    if body.sequence <= connector.last_sequence or body.resource != connector.resource:
        raise HTTPException(409, "Observation replayed or outside resource scope")
    env = session.get(Environment, connector.environment_id)
    if env.resource_scope and connector.resource not in env.resource_scope:
        raise HTTPException(403, "Connector resource no longer authorized")
    connector.last_sequence, connector.last_seen_at, connector.version = body.sequence, now(), body.version
    session.add(
        Observation(
            tenant_id=connector.tenant_id,
            environment_id=connector.environment_id,
            source="linux-connector",
            resource=connector.resource,
            observed_at=body.observed_at,
            quality="partial",
            data=body.diagnostics,
        )
    )
    env.last_observed_at, env.health = body.observed_at, "DEGRADED"
    session.commit()
    return {"status": "accepted", "sequence": body.sequence}


@router.post("/action-proposals/{proposal_id}/reconcile")
def reconcile_action(
    proposal_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    from atlasops.actions import reconcile

    result = reconcile(session, p, str(proposal_id))
    session.commit()
    return public_record(result)


from atlasops.diagnostics import EvidenceQuery  # noqa: E402


@router.post("/diagnostics/query")
def diagnostic_query(
    body: EvidenceQuery, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    from atlasops.diagnostics import run_diagnostic

    result = run_diagnostic(session, p, body)
    session.commit()
    return {"items": result}


@router.get("/environments/{environment_id}/resources")
def environment_resources(
    environment_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)
):
    scoped_get(session, Environment, str(environment_id), p)
    query = scoped_query(Observation, p).where(Observation.environment_id == str(environment_id))
    records = session.scalars(
        query.distinct(Observation.resource)
        .order_by(Observation.resource, Observation.observed_at.desc())
        .limit(100)
    ).all()
    return {"items": [public_record(r) for r in records], "total": len(records), "limit": 100, "offset": 0}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: UUID, p: Principal = Depends(current_user), session: Session = Depends(get_session)):
    p.require("operate")
    job = scoped_get(session, BackgroundJob, str(job_id), p, for_update=True)
    if job.payload.get("actor_id") != p.user_id:
        raise HTTPException(403, "Only the requester may cancel a pending job")
    if job.status not in {"PENDING", "RETRY"}:
        raise HTTPException(409, "Only work that has not started can be cancelled")
    job.status = "CANCELLED"
    job.completed_at = now()
    audit(session, p, "job.cancelled", job)
    session.commit()
    return {"status": "CANCELLED"}
