from datetime import timedelta
from zoneinfo import ZoneInfo

from celery import Celery
from sqlalchemy import select

from atlasops.actions import transition
from atlasops.auth import resolve_principal
from atlasops.config import settings
from atlasops.db import transaction
from atlasops.jobs import enqueue, process_job, recover_stalled_jobs
from atlasops.logging import configure_logging
from atlasops.models import ActionProposal, AuditEvent, BackgroundJob, Integration, Membership, now

configure_logging()
celery = Celery("atlasops", broker=settings().redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=90,
    task_time_limit=120,
    broker_connection_retry_on_startup=True,
    beat_schedule={"durable-dispatch": {"task": "atlasops.dispatch", "schedule": 10.0}},
    timezone="UTC",
    task_ignore_result=True,
)


@celery.task(name="atlasops.run_job")
def run_job(job_id):
    process_job(job_id)


@celery.task(name="atlasops.dispatch")
def dispatch():
    recover_stalled_jobs()
    with transaction() as session:
        expired = session.scalars(
            select(ActionProposal)
            .where(
                ActionProposal.state.in_(["AWAITING_APPROVAL", "APPROVED"]),
                ActionProposal.expires_at <= now(),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for proposal in expired:
            transition(proposal, "EXPIRED")
            session.add(
                AuditEvent(
                    tenant_id=proposal.tenant_id,
                    environment_id=proposal.environment_id,
                    actor_id="system:scheduler",
                    kind="action.expired",
                    object_id=proposal.id,
                    data={},
                )
            )
        # Select an active tenant-wide report-capable identity; authorization is rechecked when jobs run.
        memberships = session.scalars(select(Membership).where(Membership.role == "administrator")).all()
        local = now().astimezone(ZoneInfo(settings().report_timezone))
        tenants = set()
        for member in memberships:
            if member.tenant_id in tenants or "*" not in member.environment_ids:
                continue
            try:
                principal = resolve_principal(session, member.user_id, member.tenant_id)
            except Exception:
                continue
            tenants.add(member.tenant_id)
            if local.hour >= settings().report_hour:
                day = (local.date() - timedelta(days=1)).isoformat()
                enqueue(session, principal, "report", {"day": day}, f"scheduled-report:{day}")
            for integration in session.scalars(
                select(Integration).where(
                    Integration.tenant_id == member.tenant_id, Integration.provider != "alertmanager"
                )
            ):
                slot = int(now().timestamp()) // 300
                enqueue(
                    session,
                    principal,
                    "integration",
                    {"integration_id": integration.id},
                    f"integration:{integration.id}:{slot}",
                )
        due = session.scalars(
            select(BackgroundJob.id)
            .where(BackgroundJob.status.in_(["PENDING", "RETRY"]), BackgroundJob.available_at <= now())
            .limit(100)
        ).all()
    for job_id in due:
        run_job.delay(job_id)
