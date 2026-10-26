import hashlib
import hmac
import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from atlasops.adapters.http import EnvironmentSecrets
from atlasops.auth import resolve_principal
from atlasops.incidents import ingest
from atlasops.jobs import enqueue
from atlasops.models import Deployment, Integration, Membership, WebhookReceipt, now
from atlasops.schemas import IncidentInput


def receive(session, provider: str, integration_id: str, headers, body: bytes):
    integration = session.get(Integration, integration_id)
    if (
        not integration
        or integration.provider != provider
        or provider not in {"github", "jenkins", "alertmanager"}
    ):
        raise HTTPException(404, "Not found")
    if not integration.secret_ref:
        raise HTTPException(503, "Webhook signing key not configured")
    key = EnvironmentSecrets().get(integration.secret_ref).encode()
    if provider == "github":
        expected = "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()
        signature = headers.get("x-hub-signature-256", "")
    else:
        timestamp = headers.get("x-atlas-timestamp", "")
        event_id = headers.get("x-atlas-event-id", "")
        try:
            if abs(now().timestamp() - int(timestamp)) > 300 or not 1 <= len(event_id) <= 128:
                raise ValueError()
        except ValueError:
            raise HTTPException(401, "Webhook timestamp or event identifier invalid")
        expected = (
            "sha256=" + hmac.new(key, f"{timestamp}.{event_id}.".encode() + body, hashlib.sha256).hexdigest()
        )
        signature = headers.get("x-atlas-signature", "")
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Webhook signature invalid")
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError()
        if provider == "github":
            if payload.get("repository", {}).get("full_name") != integration.config["repository"]:
                raise HTTPException(403, "Webhook repository outside integration scope")
            timestamp = datetime.fromisoformat(payload["workflow_run"]["updated_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None or abs((now() - timestamp).total_seconds()) > 300:
                raise HTTPException(401, "Webhook event is stale")
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "Unsupported webhook payload")
    payload = normalized_payload(provider, payload)
    # Native GitHub does not sign the delivery-id header. Bind replay protection to the signed body itself.
    external_id = hashlib.sha256(body).hexdigest()
    receipt = session.scalar(
        insert(WebhookReceipt)
        .values(tenant_id=integration.tenant_id, integration_id=integration.id, external_id=external_id)
        .on_conflict_do_nothing(index_elements=["integration_id", "external_id"])
        .returning(WebhookReceipt.id)
    )
    if not receipt:
        return {"status": "duplicate"}
    membership = session.scalar(
        select(Membership).where(
            Membership.tenant_id == integration.tenant_id, Membership.role == "administrator"
        )
    )
    if not membership:
        raise HTTPException(503, "No configured integration administrator")
    principal = resolve_principal(session, membership.user_id, membership.tenant_id)
    if not principal.permits_environment(integration.environment_id):
        raise HTTPException(403, "Integration administrator is out of scope")
    job_id = enqueue(
        session,
        principal,
        "webhook",
        {"integration_id": integration.id, "provider": provider, "event": payload},
        f"webhook:{integration.id}:{external_id}",
    )
    integration.status, integration.last_success_at, integration.last_checked_at = "CONNECTED", now(), now()
    return {"status": "accepted", "job_id": job_id}


def apply_event(session, principal, payload):
    from atlasops.access import scoped_get

    integration = scoped_get(session, Integration, payload["integration_id"], principal)
    data, provider = payload["event"], payload["provider"]
    if provider == "alertmanager":
        alerts = data.get("alerts", [])
        if not isinstance(alerts, list) or len(alerts) > 100:
            raise HTTPException(422, "Invalid alert batch")
        for alert in alerts:
            labels, annotations = alert.get("labels", {}), alert.get("annotations", {})
            fingerprint = (
                alert.get("fingerprint")
                or hashlib.sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest()
            )
            title = str(annotations.get("summary", labels.get("alertname", "Monitoring alert")))[:255]
            # A resolved notification is evidence, not proof of service recovery.
            severity = {"critical": "critical", "warning": "medium", "info": "low"}.get(
                labels.get("severity"), "high"
            )
            ingest(
                session,
                principal,
                IncidentInput(
                    environment_id=integration.environment_id,
                    title=title,
                    severity=severity,
                    source="alertmanager",
                    external_id=fingerprint,
                    evidence={
                        "metric": labels.get("alertname", "unknown"),
                        "reference": str(alert.get("generatorURL", ""))[:2000],
                    },
                ),
            )
        return
    if provider == "github":
        run = data["workflow_run"]
        values = {
            "external_id": f"{integration.id}:github:{run['id']}",
            "repository": integration.config["repository"],
            "revision": run["head_sha"],
            "branch": run.get("head_branch", ""),
            "workflow": run["name"],
            "status": run.get("conclusion") or run["status"],
            "run_url": run["html_url"],
            "observed_at": datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00")),
        }
    else:
        # Signed relay contract is documented; Jenkins has no universal native HMAC webhook format.
        run = data["build"]
        values = {
            "external_id": f"{integration.id}:jenkins:{data['name']}:{run['number']}",
            "workflow": str(data["name"])[:255],
            "revision": str(run.get("revision", ""))[:160],
            "repository": str(run.get("repository", ""))[:255],
            "branch": str(run.get("branch", ""))[:160],
            "status": str(run["status"])[:32],
            "run_url": str(run.get("url", ""))[:2048],
            "observed_at": datetime.fromtimestamp(float(run["timestamp"]) / 1000, UTC),
        }
    session.execute(
        insert(Deployment)
        .values(
            tenant_id=principal.tenant_id,
            environment_id=integration.environment_id,
            provider=provider,
            **values,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "external_id"],
            set_={"status": values["status"], "observed_at": values["observed_at"]},
        )
    )


def normalized_payload(provider: str, payload: dict) -> dict:
    """Retain only fields consumed by normalization, rather than complete external request bodies."""
    try:
        if provider == "github":
            run = payload["workflow_run"]
            keys = ["id", "name", "head_sha", "head_branch", "status", "conclusion", "html_url", "updated_at"]
            return {
                "workflow_run": {k: run.get(k) for k in keys},
                "repository": {"full_name": payload["repository"]["full_name"]},
            }
        if provider == "jenkins":
            run = payload["build"]
            keys = ["number", "status", "timestamp", "url", "revision", "repository", "branch"]
            if not all(k in run for k in ["number", "status", "timestamp"]):
                raise ValueError()
            return {"name": str(payload["name"])[:255], "build": {k: run[k] for k in keys if k in run}}
        alerts = payload["alerts"]
        if not isinstance(alerts, list) or len(alerts) > 100:
            raise ValueError()
        return {
            "alerts": [
                {
                    "fingerprint": str(alert.get("fingerprint", ""))[:128],
                    "labels": {
                        k: str(v)[:255]
                        for k, v in alert.get("labels", {}).items()
                        if k in {"alertname", "severity", "service", "resource"}
                    },
                    "annotations": {
                        "summary": str(alert.get("annotations", {}).get("summary", "Monitoring alert"))[:255]
                    },
                    "generatorURL": safe_reference(str(alert.get("generatorURL", ""))),
                }
                for alert in alerts
            ]
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HTTPException(422, "Unsupported webhook payload")


def safe_reference(url):
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        return ""
    return urlunsplit((parsed.scheme, parsed.hostname, parsed.path, "", ""))[:2000]
