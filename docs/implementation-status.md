# AtlasOps AI implementation status

Validated 26 October 2026. The initial repository was empty. The repository now contains a runnable development/pilot application; the full production vision is **not** claimed complete. No production deployment, Terraform apply, Git push or live cloud mutation was performed.

## Delivered and wired into the application

- FastAPI versioned API, PostgreSQL operational schema and checked-in Alembic migration; independently runnable API, Celery worker and scheduler; Redis dispatch with durable database jobs.
- Production OIDC JWT validation and opt-in development authentication; persisted tenant/environment membership, explicit RBAC, tenant-scoped object access, validation redaction and JSON logs.
- React/TypeScript dashboard with real API data: overview, environments, services, incident list/detail/timeline/evidence, investigations, approval inbox/confirmation, deployment history, daily reports, integration configuration and audit trail. React Router, TanStack Query, accessible modal controls, Zod/react-hook-form validation, Recharts, local fonts, responsive layout and real loading/error/empty states.
- Typed adapter contracts and replaceable factories for infrastructure, observability, CI/CD, secrets, AI, notifications and constrained execution.
- Read-only AWS EC2 inventory and CloudWatch helpers; Prometheus/Grafana adapters; Jenkins/GitHub run observation and signed event ingestion; scoped/revocable outbound Linux diagnostics.
- Deduplicated incident ingestion, legal incident transitions, bounded audited evidence queries, structured AI-provider abstraction, validated evidence references and explicit insufficient-evidence/AI-unavailable outcomes. No AI output can authorize execution.
- Canonical hashed action plans, explicit human decisions, scope/permission/expiry/precondition revalidation, transactional one-time consumption, sandbox execution, independent target verification, uncertainty recording and read-only reconciliation. Production-changing handlers are unsupported.
- Durable reports with timezone-aware windows, data coverage, incident/deployment/action outcomes, scheduled generation, independent SMTP delivery and bounded retry/failure records. Safe cancellation of unstarted jobs and stalled-job recovery.
- Docker development stack; optional Prometheus/Grafana/Alertmanager/OTel Collector/Loki/Tempo profile with datasource/dashboard provisioning, scrape and alert rules; optional Terraform IAM discovery role.
- Architecture, threat/security model, API/adapter guides, setup, deployment, IAM, connector, AI/webhook/report configuration, backup/restore and troubleshooting documentation.

## Actual verification

| Check | Result |
|---|---|
| PostgreSQL backend suite | **49 passed**, no skips; real local PostgreSQL, separate `atlasops_test` database |
| Approval negative/security checks | Passed: no approval, rejection, expiry, changed plan/target/operation, unauthorized or cross-tenant decision, unsafe parameters, concurrent duplicate use, current membership, changed preconditions, failed verification, uncertain results and reconciliation |
| OIDC checks | RSA signature, issuer, audience and expiry validated with a generated test signing key; live identity provider not configured |
| Migration checks | Initial upgrade, downgrade-to-base/upgrade roundtrip on the expendable test database, and schema-drift check passed |
| Browser tests | **2 passed** against actual API, worker, scheduler, PostgreSQL and Redis: full synthetic alert → investigation → proposal → confirmed approval → verified execution → report; tablet navigation. Each run uses an isolated synthetic tenant. |
| Frontend | Strict TypeScript and production Vite build passed; chart/form bundles split; self-hosted fonts |
| Python static checks | Ruff lint and format checks passed |
| Installation/startup repeatability | Full install script rerun preserved `.env` and existing data; idempotent process startup/restart and API/frontend functional requests passed |
| Container pilot | API and web images built with TLS verification and hash-locked Python packages; API, web, worker, scheduler, PostgreSQL and Redis health checks passed on alternate local pilot ports |
| Actual read-only telemetry | A separate local Linux connector process delivered actual `/proc`/disk diagnostics to the API; resource read verified and test credential revoked. Managed Prometheus supplied fresh actual AtlasOps scrape observations through the application's adapter. |
| Optional monitoring | Prometheus config/3 rules validated; AtlasOps scrape `up=1`; Grafana health, Alertmanager readiness, Loki readiness and collector/Tempo startup verified |
| CI/CD contracts | Local HTTP doubles for GitHub/Jenkins, signed native GitHub and signed Jenkins/Alertmanager relay fixtures, replay/freshness rejection and durable normalization passed |
| Reports/mail | Timezone/DST window tests, duplicate scheduling, actual local SMTP delivery through durable jobs, failure/retry and report preservation passed |
| Dependency scans | `npm audit` (all dependencies): zero reported advisories; `pip-audit` across the installed Python environment: zero reported advisories. These are dependency-database checks, not proof of absence of vulnerabilities or a base-image security certification. |
| Terraform | `fmt`, provider initialization and `validate` passed; no plan/apply against AWS |

One upstream Starlette test-client deprecation warning remains (its current release warns about httpx/httpx2); it does not skip or fail tests. Vite reports a dependency comment-annotation warning in Zod 4 while producing a valid build.

## Milestone gates and remaining work

1. **Foundation:** pilot gate met.
2. **Read-only inventory/observability:** local telemetry gate met; live AWS and private production-host acceptance remain unverified. Connector sends log references; remote log payload retrieval and job execution are not implemented.
3. **Investigation:** evidence collection, constrained output and no-provider behavior verified. A live model, deeper trace/deployment/service-dependency correlation, an autonomous multi-step diagnostic planner, and evidence-backed real root-cause acceptance remain outstanding. Do not label the evidence-only result a completed AI diagnosis.
4. **Approval/constrained execution:** sandbox gate met, including mandatory negative tests. No production mutation capability is enabled or advertised.
5. **CI/CD/reporting:** local contract/scheduling/SMTP gate met. External Jenkins/GitHub API/webhook delivery and production SMTP acceptance remain unverified.
6. **Hardening/pilot:** local pilot, monitoring profile, documentation and test gates completed. Production rollout is outstanding.

## Explicit limitations

- No live AWS, production CI/CD, paid LLM, production SMTP or external OIDC configuration was supplied. Test doubles are explicitly synthetic; no external integration success is fabricated.
- UI user administration, connector enrollment/rotation screens, full OIDC redirect/PKCE login, advanced service/dependency views and larger environment/service catalog pagination are not implemented; documented authenticated API/CLI workflows exist where stated.
- Monitoring coverage remains conservatively partial/UNKNOWN or DEGRADED. No complete historical coverage, service-health proof, SLO evaluation, trend prediction or incident resolution is inferred from no alerts or a successful handler response.
- Database RLS, dedicated deployment IAM/database roles, externally retained immutable audit storage, automatic retention/deletion, HA/failover, object storage and restore drills require production engineering and operator configuration.
- OTel API instrumentation is installed and the optional collector/Tempo pipeline runs; an application exporter/worker spans and log shipping are not fully wired. Monitoring readiness is not proof of trace/log ingestion.
- Jenkins/Alertmanager require the documented signing relay; native unsigned webhooks are rejected. GitHub's unsigned delivery timestamp limitation is documented.
- SMTP acknowledgement loss can produce duplicate email after retry; deterministic Message-ID does not guarantee exactly-once SMTP delivery.
- Reports are retained snapshots for a window/scope; regenerating an existing window returns that snapshot. Current-day snapshots are necessarily partial.
- Docker images are pinned for reproducibility; review base-image advisories and the operational patch policy before exposing any service outside a pilot network.
- Repository files are local/uncommitted. The remote still had no `main` during initial inspection. Filesystem preparation and a saved cloud draft do not establish a Git push, environment publication or fresh-task restoration.

## Exact next implementation task

Wire an operator-selected live OIDC provider with frontend authorization-code/PKCE login and verify the complete tenant membership flow against it. Then run the documented read-only AWS, CI/CD, LLM and SMTP acceptance checks with securely configured least-privilege bindings. Keep production-changing handlers disabled until their own integration, policy and recovery gates pass.
