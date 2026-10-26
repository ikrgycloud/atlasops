import hashlib
import json
import smtplib
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import select

from atlasops.access import scoped_query
from atlasops.adapters.contracts import AdapterError, Capabilities, NotificationAdapter
from atlasops.adapters.http import EnvironmentSecrets
from atlasops.config import settings
from atlasops.models import (
    ActionExecution,
    ActionProposal,
    Deployment,
    Environment,
    Incident,
    Integration,
    Investigation,
    NotificationDelivery,
    Observation,
    Report,
    now,
)


def scope_key(principal):
    return hashlib.sha256(json.dumps(sorted(principal.environment_ids)).encode()).hexdigest()


def report_window(day=None, at=None):
    zone = ZoneInfo(settings().report_timezone)
    local_date = date.fromisoformat(day) if day else (at or now()).astimezone(zone).date() - timedelta(days=1)
    start = datetime.combine(local_date, time.min, zone).astimezone(UTC)
    end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(UTC)
    return start, end


def coverage(session, principal, start, end):
    env_query = scoped_query(Environment, principal)
    if "*" not in principal.environment_ids:
        env_query = env_query.where(Environment.id.in_(principal.environment_ids))
    envs = session.scalars(env_query).all()
    integrations = session.scalars(scoped_query(Integration, principal)).all()
    observations = session.scalars(
        scoped_query(Observation, principal).where(
            Observation.observed_at >= start, Observation.observed_at < end
        )
    ).all()
    sources = sorted({o.source for o in observations})
    latest = max((o.observed_at for o in observations), default=None)
    missing = []
    for env in envs:
        relevant = [o for o in observations if o.environment_id == env.id and o.quality != "synthetic"]
        if not relevant:
            missing.append(f"{env.name}: no authorized real telemetry in reporting window")
    unavailable = [i.name for i in integrations if i.status != "CONNECTED"]
    if unavailable:
        missing.append("Unavailable integrations: " + ", ".join(unavailable))
    # Current probe status cannot demonstrate historical continuous monitoring or an SLO.
    complete = False
    status = "DEGRADED" if observations else "UNKNOWN"
    return {
        "status": status,
        "complete": complete,
        "sources_queried": sources,
        "most_recent_observation": latest.isoformat() if latest else None,
        "missing_telemetry": missing or ["Continuous historical coverage is not established"],
        "unavailable_integrations": unavailable,
        "observations": len(observations),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "synthetic_observations": sum(o.quality == "synthetic" for o in observations),
    }


def generate_report(session, principal, day=None):
    principal.require("report")
    start, end = report_window(day)
    key = scope_key(principal)
    existing = session.scalar(
        select(Report).where(
            Report.tenant_id == principal.tenant_id,
            Report.window_start == start,
            Report.window_end == end,
            Report.scope_key == key,
        )
    )
    if existing:
        return existing

    def records(model, time_column):
        return session.scalars(
            scoped_query(model, principal).where(time_column >= start, time_column < end)
        ).all()

    incidents = records(Incident, Incident.first_observed_at)
    deployments = records(Deployment, Deployment.observed_at)
    actions = records(ActionProposal, ActionProposal.created_at)
    executions = records(ActionExecution, ActionExecution.created_at)
    findings = records(Investigation, Investigation.created_at)
    data = {
        "title": "Daily operations report",
        "timezone": settings().report_timezone,
        "coverage": coverage(session, principal, start, end),
        "incidents_by_severity": dict(Counter(i.severity for i in incidents)),
        "incidents": [
            {
                "id": i.id,
                "title": i.title,
                "severity": i.severity,
                "status": i.status,
                "environment_id": i.environment_id,
            }
            for i in incidents
        ],
        "deployments": [
            {
                "revision": d.revision,
                "workflow": d.workflow,
                "status": d.status,
                "provider": d.provider,
                "run_url": d.run_url,
            }
            for d in deployments
        ],
        "actions": [{"id": a.id, "state": a.state, "plan_hash": a.plan_hash} for a in actions],
        "executions": [
            {"proposal_id": e.proposal_id, "status": e.status, "result": e.result} for e in executions
        ],
        "findings": [
            {"incident_id": f.incident_id, "status": f.status, "findings": f.findings} for f in findings
        ],
        "unresolved_incidents_snapshot": 0,
        "environment_scope": list(principal.environment_ids),
        "snapshot_at": now().isoformat(),
        "follow_up": [
            "Review missing telemetry and unavailable integrations",
            "Review unresolved incidents and approvals",
        ],
        "slo_assessment": "UNKNOWN: no SLO configuration has been established",
        "infrastructure_trends": "Insufficient historical sampling for trend or risk prediction",
    }
    data["unresolved_incidents_snapshot"] = len(
        session.scalars(
            scoped_query(Incident, principal).where(Incident.status.not_in(["RESOLVED", "CLOSED"]))
        ).all()
    )
    data["pending_approvals_snapshot"] = len(
        session.scalars(
            scoped_query(ActionProposal, principal).where(ActionProposal.state == "AWAITING_APPROVAL")
        ).all()
    )
    data["summary"] = (
        f"{len(incidents)} incidents, {len(deployments)} deployment events, "
        f"{sum(e.status == 'SUCCEEDED' for e in executions)} verified sandbox actions. "
        "Evidence coverage is partial; service health is not established."
    )
    from sqlalchemy.dialects.postgresql import insert

    object_id = session.scalar(
        insert(Report)
        .values(tenant_id=principal.tenant_id, scope_key=key, window_start=start, window_end=end, data=data)
        .on_conflict_do_nothing(index_elements=["tenant_id", "window_start", "window_end", "scope_key"])
        .returning(Report.id)
    )
    return (
        session.get(Report, object_id)
        if object_id
        else session.scalar(
            select(Report).where(
                Report.tenant_id == principal.tenant_id,
                Report.window_start == start,
                Report.window_end == end,
                Report.scope_key == key,
            )
        )
    )


class SMTPNotification:
    capabilities = Capabilities(frozenset({"email.send"}))

    def send(self, recipient: str, subject: str, body: str, message_id: str):
        config = settings()
        if not config.smtp_host or not recipient:
            raise AdapterError("smtp_not_configured")
        if config.smtp_host not in {x.strip() for x in config.integration_hosts.split(",")}:
            raise AdapterError("destination_not_allowed")
        if config.mode == "production" and not config.smtp_starttls:
            raise AdapterError("smtp_tls_required")
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = config.smtp_sender, recipient, subject
        message["Message-ID"] = f"<{message_id}@atlasops.local>"
        message.set_content(body)
        try:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as server:
                server.ehlo()
                if config.smtp_starttls:
                    import ssl

                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if config.smtp_username:
                    server.login(config.smtp_username, EnvironmentSecrets().get(config.smtp_password_ref))
                server.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise AdapterError("smtp_delivery_failed", retryable=True)


def deliver_report(session, delivery_id, notification: NotificationAdapter | None = None):
    delivery = session.scalar(
        select(NotificationDelivery).where(NotificationDelivery.id == delivery_id).with_for_update()
    )
    if delivery.status == "SENT":
        return
    report = session.get(Report, delivery.report_id)
    delivery.attempts += 1
    try:
        (notification or SMTPNotification()).send(
            delivery.recipient,
            f"AtlasOps · {report.window_start.date()} operations report",
            report.data["summary"] + "\n\n" + json.dumps(report.data, indent=2),
            delivery.id,
        )
        delivery.status, delivery.error_code = "SENT", None
    except AdapterError as error:
        delivery.status, delivery.error_code = "FAILED", error.code
        # Caller commits this delivery record before arranging a retry.
