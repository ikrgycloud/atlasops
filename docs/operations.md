# Development and deployment operations

## Files and processes

`backend/atlasops`: domain services, policy/authentication, typed adapters, API and Celery processes. `backend/migrations`: versioned PostgreSQL schema. `frontend/src`: API-backed React dashboard. `connectors/linux`: separate outbound Linux diagnostic process. `infra/observability`: optional local monitoring stack. `infra/terraform`: optional read-only AWS discovery role. `scripts`: repeatable setup and local process control. `.local` and `.env` are ignored private development state.

Retained dependencies/files do not imply retained processes. Run `bash scripts/install.sh` to refresh installation and `.venv/bin/python scripts/local_services.py start` after restoring a task snapshot. No worktree is needed in an isolated cloud task. PostgreSQL/Redis use Docker volumes; live connections and processes must restart. If a cloud snapshot does not retain Docker volumes, recover the database from a verified backup or run development migrations/seed on a new empty database. Never imply a published filesystem snapshot is a tested disaster-recovery backup.

## Configuration and authentication

Production is the default mode. Require a valid database URL and OIDC issuer, audience and JWKS URL. Production disables development authentication and insecure integration HTTP. Use TLS URLs for the issuer/JWKS service, trusted DNS/egress restrictions, a dedicated tenant membership provisioning process and short-lived provider access tokens. Map a verified subject to a persisted user, then provision its membership using:

```bash
.venv/bin/python -m atlasops.cli provision-user --email USER --subject VERIFIED_OIDC_SUB --tenant TENANT --role viewer
```

Roles and environment grants are loaded on every request; a stale token does not retain a revoked membership. OIDC tokens must contain a tenant `tid` claim or the client must supply `X-Tenant-Id` for a tenant where that identity has membership. The development web UI supports a provider-issued bearer token, but does not yet implement an OIDC redirect/PKCE login flow. In production integrate your supported identity-provider login at ingress or extend the frontend with PKCE before broad rollout. Do not store credentials in browser bundles.

A separate least-privilege database role should own migrations. The application role needs operational CRUD, with INSERT/SELECT only on audit events. Revoke audit UPDATE/DELETE and DDL from runtime accounts. This pilot enforces tenancy in application queries plus scoped foreign keys; PostgreSQL RLS is not enabled because pool/session tenant-context management has not been implemented and verified. Restrict direct database access. User/membership changes currently require an operator-controlled provisioning procedure; there is no public role-administration endpoint.

Set `ATLAS_ALLOWED_HOSTS` to the deployed control-plane hostnames. No cross-origin browser API access is enabled. Bearer authentication avoids ambient cookie/CSRF credentials; frontend tokens use session storage, so use CSP, trusted assets, TLS, short expiry and a secure OIDC login. Nginx provides CSP and other security headers. Apply production request/rate limits at ingress; the built-in authentication limiter is a per-process development limiter only. Do not expose `/metrics`, PostgreSQL, Redis, or managed observability publicly.

## Migrations

Run `alembic -c backend/alembic.ini upgrade head` from the repository root after installation. Schema is established by a checked-in Alembic revision; application startup does not call `create_all()`. `alembic ... check` detects ORM/schema drift. Review and back up before applying a migration to a real deployment. Test upgrade/downgrade on an expendable database before production changes; never downgrade a database with operational data without a recovery plan.

## Background reliability

Redis dispatches JSON-only Celery tasks. PostgreSQL holds all job/business state. Beat sweeps due jobs every 10 seconds and schedules five-minute integration probes and morning reports. Concurrent deliveries are safely claimed under row locks; business handlers use stable keys. Retryable read/mail errors receive bounded backoff/jitter, with terminal failures retained for review. A worker interruption after a mutation claim creates `RECONCILIATION_REQUIRED`, not a mutation retry. `/action-proposals/{id}/reconcile` reads the sandbox target without reexecuting it. A failed operation requires a new proposal/approval if another attempt is appropriate.

Run one scheduler per deployment, even though database idempotency prevents duplicate business records. Use a supervised worker deployment, resource/time limits, Redis authentication/TLS, queue monitoring, PostgreSQL backups and graceful worker shutdown. Cancellation is permitted only before safe work begins; do not kill executing infrastructure handlers as a cancellation strategy.

## Optional managed observability

Generate a separate private Grafana password (do not put it in Git). From the repository root:

```bash
# Supply GRAFANA_ADMIN_PASSWORD securely through your shell or a private env file.
docker compose --project-name atlasops-observability --env-file PRIVATE_ENV_FILE \
  -f infra/observability/compose.yml --profile observability up -d
```

The profile pins Prometheus, Grafana, Alertmanager, OTel Collector, Loki and Tempo versions. It provisions datasources, an AtlasOps dashboard, a 15-second scrape, and API/job alert rules. Public config files must be readable by the images' non-root users (0644 files/0755 directories); no secret should be placed in those files. Native AtlasOps binds port 8000 on the task's network to permit the isolated Prometheus container's host-gateway scrape. Restrict this port with host/network policy outside an isolated development task. Include `host.docker.internal` in allowed hosts for that route. If deploying API and monitoring together, prefer an internal network/service DNS scrape.

The collector accepts OTLP HTTP and forwards traces to Tempo. The API has OpenTelemetry FastAPI instrumentation; an application OTLP exporter and worker span export need production wiring. Loki has no automatic host-log shipper configured. Grafana datasource health and server readiness are useful checks but do not prove traces or logs have been ingested. This profile is single-node development infrastructure, with no HA or production retention guarantee. Configure a trusted signing relay before forwarding Alertmanager events to AtlasOps.

Validate Prometheus config/rules with its image's `/bin/promtool`. Grafana local health, Prometheus `up`, Loki readiness and collector/Tempo startup were exercised; see status for current results. Old pinned image versions must be reviewed/scanned and updated according to your deployment's patch policy before external exposure.

## Cloud proxy builds

In this cloud machine Docker builds do not automatically inherit the host's proxy DNS or trust bundle. A tested private override `.local/cloud-build.json` supplies the existing HTTP/HTTPS proxy build args, a resolved proxy host mapping, and the platform CA as a BuildKit secret named `proxy_ca`. The Dockerfiles use that CA only for verified package download operations. The CA is not embedded as an application secret and credential values are not included in tracked files.

```bash
DOCKER_CONFIG="$PWD/.local/docker" docker compose -f docker-compose.yml \
  -f .local/cloud-build.json --profile app build api web
```

The override is specific to this running machine; recreate it from the platform's existing proxy host and CA path when necessary. On ordinary Docker hosts without this proxy, the normal build works without that optional secret. Do not use `--trusted-host`, `strict-ssl=false`, `verify=False` or checksum bypasses. Package caches belong under writable workspace paths in this cloud environment, not the read-only home directory.

## Backup, restore and retention

Back up PostgreSQL with `pg_dump --format=custom` using a dedicated backup account and secure credential injection. Store encrypted backups outside the instance with retention and restore monitoring. Protect the dump file: operational evidence and tenant identities may be sensitive. To test restore, create an isolated empty database, use `pg_restore --no-owner --no-acl`, verify Alembic revision, then run read-only integrity/tenant checks and a sandbox workflow. Never restore over an existing deployment without authorization. Capture Redis queue settings, provider references and runtime configuration separately; PostgreSQL is authoritative for recovery dispatch.

Reports, evidence references, jobs and audit events currently have no automatic deletion policy. Define contractual retention windows and implement an audited, tenant-scoped deletion/export procedure before collecting production data. Large logs remain in their authorized source. For stronger audit integrity, forward append-only audit events to externally retained WORM/object-lock storage; ordinary logs and PostgreSQL rows alone are not tamper-proof.

## Troubleshooting

- Readiness 503: check PostgreSQL, `alembic_version`, Redis connectivity, and service logs; no readiness claim follows a PID alone.
- Empty/UNKNOWN dashboard: register a permitted source and test it. Missing evidence is never HEALTHY.
- Pending jobs: API, worker and scheduler are separate processes. Inspect `.local/worker.log`, `.local/scheduler.log`, job status and broker health.
- Permission errors: inspect the current user's tenant membership and environment grants. A token is not a stored permission snapshot.
- Expired/altered approval: make a new plan; do not edit the database hash or replay a consumed approval.
- Reconciliation required: inspect/verify the target through the read-only reconciliation endpoint; never retry the mutation blindly.
- Integration rejection: allow only the required destination hostname and use a supported TLS/auth configuration. Distinguish permission denials, missing bindings and transport errors.
- Connector rejected: verify resource scope, UTC timestamp, persisted sequence, revocation and token rotation; never print the credential.
- Docker permission denied: ensure public config files are readable by non-root image users; keep `.env` private.

## Deployment scope

This repository prepares a development/pilot deployment. It does not automatically publish the cloud environment, push Git commits, apply Terraform, provision production services, configure a live identity provider, or enable real infrastructure-changing handlers. Production release work includes external integration acceptance, PKCE login, runtime IAM/DB hardening, secret-manager bindings, egress enforcement, workload/backup/restore drills, vulnerability review and operational ownership.
