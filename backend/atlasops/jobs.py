import random
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from atlasops.access import audit, scoped_get
from atlasops.actions import execute, transition
from atlasops.adapters.contracts import AdapterError
from atlasops.adapters.registry import ai_provider
from atlasops.auth import resolve_principal
from atlasops.db import transaction
from atlasops.incidents import event
from atlasops.models import (
    ActionExecution,
    ActionProposal,
    BackgroundJob,
    Environment,
    Incident,
    Integration,
    Investigation,
    NotificationDelivery,
    now,
)
from atlasops.reporting import deliver_report, generate_report
from atlasops.schemas import Finding


def enqueue(session, principal, kind: str, payload: dict, key: str):
    job_id = session.scalar(
        insert(BackgroundJob)
        .values(
            tenant_id=principal.tenant_id,
            kind=kind,
            payload={**payload, "actor_id": principal.user_id},
            idempotency_key=key,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "idempotency_key"])
        .returning(BackgroundJob.id)
    )
    return job_id or session.scalar(
        select(BackgroundJob.id).where(
            BackgroundJob.tenant_id == principal.tenant_id, BackgroundJob.idempotency_key == key
        )
    )


def process_job(job_id: str):
    with transaction() as session:
        job = session.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update())
        if not job or job.status not in {"PENDING", "RETRY"} or job.available_at > now():
            return
        job.status, job.started_at, job.attempts = "RUNNING", now(), job.attempts + 1
        kind, payload, tenant_id = job.kind, job.payload, job.tenant_id
    try:
        if kind == "execute":
            result = execute(payload["proposal_id"], payload["actor_id"], tenant_id)
            if result["status"] != "SUCCEEDED":
                raise AdapterError("execution_" + result["status"].lower())
        else:
            with transaction() as session:
                principal = resolve_principal(session, payload["actor_id"], tenant_id)
                if kind == "investigate":
                    principal.require("operate")
                    investigation = scoped_get(
                        session, Investigation, payload["investigation_id"], principal, for_update=True
                    )
                    incident = scoped_get(session, Incident, investigation.incident_id, principal)
                    from atlasops.diagnostics import EvidenceQuery, run_diagnostic

                    evidence = run_diagnostic(
                        session,
                        principal,
                        EvidenceQuery(
                            incident_id=incident.id,
                            start=max(
                                incident.first_observed_at - timedelta(minutes=30), now() - timedelta(hours=2)
                            ),
                            end=now(),
                        ),
                    )
                    from atlasops.config import settings

                    if settings().ai_url:
                        finding = ai_provider().investigate(evidence)
                        investigation.status = "COMPLETED"
                    else:
                        finding = Finding(
                            classification="insufficient_evidence",
                            confidence=0,
                            summary="AI investigation is unavailable. Authorized evidence has been collected for human review.",
                            evidence_ids=[e["id"] for e in evidence],
                            missing_data=[
                                "No AI provider configured",
                                "Correlated traces and dependency evidence required",
                            ],
                            next_queries=[
                                "Compare deployment revision with error-rate and latency observations"
                            ],
                        )
                        investigation.status = "AI_UNAVAILABLE"
                    investigation.findings = {
                        **finding.model_dump(),
                        "evidence": evidence,
                        "window_start": (incident.first_observed_at - timedelta(minutes=30)).isoformat(),
                        "window_end": now().isoformat(),
                    }
                    incident.status = "INVESTIGATING"
                    event(
                        session,
                        incident,
                        "investigation",
                        "Evidence collection completed",
                        {"investigation_id": investigation.id},
                    )
                    audit(session, principal, "investigation.completed", investigation)
                elif kind == "report":
                    report = generate_report(session, principal, payload.get("day"))
                    audit(session, principal, "report.generated", report)
                    from atlasops.config import settings

                    recipient = settings().report_recipient
                    # Scheduled email is tenant-wide only, never a scoped user's report to a shared recipient.
                    if recipient and "*" in principal.environment_ids:
                        delivery_id = session.scalar(
                            insert(NotificationDelivery)
                            .values(tenant_id=tenant_id, report_id=report.id, recipient=recipient)
                            .on_conflict_do_nothing(index_elements=["report_id", "recipient"])
                            .returning(NotificationDelivery.id)
                        )
                        if delivery_id:
                            enqueue(
                                session,
                                principal,
                                "email",
                                {"delivery_id": delivery_id},
                                f"email:{delivery_id}",
                            )
                elif kind == "email":
                    principal.require("report")
                    delivery = session.get(NotificationDelivery, payload["delivery_id"])
                    if (
                        not delivery
                        or delivery.tenant_id != tenant_id
                        or "*" not in principal.environment_ids
                    ):
                        raise HTTPException(403, "Notification scope denied")
                    deliver_report(session, delivery.id)
                elif kind == "integration":
                    principal.require("configure")
                    from atlasops.integrations import probe

                    integration = scoped_get(session, Integration, payload["integration_id"], principal)
                    environment = scoped_get(session, Environment, integration.environment_id, principal)
                    result = probe(session, integration, environment)
                    audit(session, principal, "integration.probed", integration, result)
                elif kind == "webhook":
                    from atlasops.webhooks import apply_event

                    principal.require("configure")
                    apply_event(session, principal, payload)
                else:
                    raise AdapterError("unsupported_job")
        with transaction() as session:
            job = session.get(BackgroundJob, job_id)
            # Delivery failed state must survive retries independently from the report.
            if kind == "email":
                delivery = session.get(NotificationDelivery, payload["delivery_id"])
                if delivery.status != "SENT":
                    raise AdapterError(delivery.error_code or "email_failed", retryable=True)
            job.status, job.completed_at, job.error_code = "SUCCEEDED", now(), None
    except Exception as error:
        with transaction() as session:
            job = session.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update())
            retryable = isinstance(error, AdapterError) and error.retryable and kind != "execute"
            job.error_code = error.code if isinstance(error, AdapterError) else "job_failed"
            job.status = "RETRY" if retryable and job.attempts < 4 else "FAILED"
            job.available_at = now() + timedelta(seconds=min(300, 2**job.attempts * 5) + random.randint(0, 5))
            if job.status == "FAILED":
                job.completed_at = now()
                if kind == "investigate":
                    investigation = session.get(Investigation, payload["investigation_id"])
                    investigation.status = "FAILED"
                    investigation.findings = {"error_code": job.error_code}


def recover_stalled_jobs():
    with transaction() as session:
        stalled = session.scalars(
            select(BackgroundJob)
            .where(BackgroundJob.status == "RUNNING", BackgroundJob.started_at < now() - timedelta(minutes=3))
            .with_for_update(skip_locked=True)
        ).all()
        for job in stalled:
            if job.kind == "execute":
                job.status = "RECONCILIATION_REQUIRED"
                proposal = session.scalar(
                    select(ActionProposal)
                    .where(ActionProposal.id == job.payload["proposal_id"])
                    .with_for_update()
                )
                if proposal.state in {"EXECUTING", "VERIFYING"}:
                    transition(proposal, "RECONCILIATION_REQUIRED")
                    execution = session.scalar(
                        select(ActionExecution).where(ActionExecution.proposal_id == proposal.id)
                    )
                    if execution:
                        execution.status = "RECONCILIATION_REQUIRED"
            else:
                job.status = "RETRY" if job.attempts < 4 else "FAILED"
                job.available_at = now()
            job.error_code = "worker_interrupted"
