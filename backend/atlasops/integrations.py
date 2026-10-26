from datetime import UTC, datetime, timedelta

from atlasops.adapters import registry
from atlasops.adapters.contracts import AdapterError
from atlasops.adapters.http import validate_url
from atlasops.models import Deployment, Observation, now

CAPABILITIES = {
    "aws": ["ec2.inventory", "cloudwatch.cpu", "cloudwatch.alarms"],
    "prometheus": ["metrics.query"],
    "grafana": ["health.read", "dashboards.list"],
    "github": ["runs.list", "webhooks.ingest"],
    "jenkins": ["runs.list", "webhooks.ingest"],
    "alertmanager": ["webhooks.ingest"],
}


def validate_integration(provider, config):
    if provider != "aws":
        validate_url(config["url"] or ("https://api.github.com" if provider == "github" else ""))
    if provider == "github" and not config["repository"]:
        raise AdapterError("repository_required")


def probe(session, integration, environment):
    checked = now()
    config, provider = integration.config, integration.provider
    records = []
    try:
        if provider == "prometheus":
            data = registry.observability(config, integration.secret_ref).query(config["query"], checked)
            if data.get("resultType") != "vector":
                raise AdapterError("instant_vector_required")
            for result in data["result"][:100]:
                observed = datetime.fromtimestamp(float(result["value"][0]), UTC)
                if observed < checked - timedelta(minutes=15) or observed > checked + timedelta(seconds=30):
                    continue
                records.append(
                    Observation(
                        tenant_id=integration.tenant_id,
                        environment_id=environment.id,
                        integration_id=integration.id,
                        source="prometheus",
                        resource=result["metric"].get("instance", "query"),
                        observed_at=observed,
                        quality="partial",
                        data={
                            "metric": config["query"],
                            "value": result["value"][1],
                            "labels": result["metric"],
                            "unit": "source-defined",
                        },
                    )
                )
            if not records:
                raise AdapterError("no_fresh_telemetry")
        elif provider == "aws":
            adapter = registry.infrastructure(config)
            inventory = adapter.inventory(environment.resource_scope)
            for item in inventory:
                records.append(
                    Observation(
                        tenant_id=integration.tenant_id,
                        environment_id=environment.id,
                        integration_id=integration.id,
                        source="aws",
                        resource=item["resource"],
                        data=item,
                        quality="partial",
                    )
                )
            if not inventory:
                raise AdapterError("no_resources_in_scope")
        elif provider == "grafana":
            adapter = registry.dashboards(config, integration.secret_ref)
            adapter.health()
            adapter.dashboards()
        elif provider in {"github", "jenkins"}:
            adapter = registry.cicd(provider, config, integration.secret_ref)
            from sqlalchemy.dialects.postgresql import insert

            for run in adapter.runs():
                observed_at = datetime.fromisoformat(run.pop("observed_at").replace("Z", "+00:00"))
                session.execute(
                    insert(Deployment)
                    .values(
                        tenant_id=integration.tenant_id,
                        environment_id=environment.id,
                        provider=provider,
                        observed_at=observed_at,
                        **run,
                    )
                    .on_conflict_do_update(
                        index_elements=["tenant_id", "external_id"],
                        set_={"status": run["status"], "observed_at": observed_at},
                    )
                )
        else:
            raise AdapterError("push_integration_requires_signed_event")
        session.add_all(records)
        integration.status = "CONNECTED"
        integration.last_success_at = checked
        integration.error_code = None
        if records:
            environment.last_observed_at = max(r.observed_at or checked for r in records)
            environment.health = "DEGRADED"  # Single-source coverage does not establish full service health.
    except AdapterError as error:
        integration.status = "UNAVAILABLE"
        integration.error_code = error.code
        environment.health = "UNKNOWN"
    integration.last_checked_at = checked
    return {
        "status": integration.status,
        "error_code": integration.error_code,
        "observations": len(records),
        "capabilities": CAPABILITIES[provider],
    }
