# AtlasOps AI implementation status

Validated 26 October 2026. The initial repository was empty. The repository now contains a runnable development/pilot application; the full production vision is **not** claimed complete. No production deployment, Terraform apply or live cloud mutation was performed. The initial pilot was pushed to `ikrgycloud/atlasops` on `main`; the OpenAI extension below records the subsequent verification.

## Delivered and wired into the application

- FastAPI versioned API, PostgreSQL operational schema and checked-in Alembic migration; independently runnable API, Celery worker and scheduler; Redis dispatch with durable database jobs.
- Production OIDC JWT validation and opt-in development authentication; persisted tenant/environment membership, explicit RBAC, tenant-scoped object access, validation redaction and JSON logs.
- React/TypeScript dashboard with real API data: overview, environments, services, incident list/detail/timeline/evidence, investigations, approval inbox/confirmation, deployment history, daily reports, integration configuration and audit trail. React Router, TanStack Query, accessible modal controls, Zod/react-hook-form validation, Recharts, local fonts, responsive layout and real loading/error/empty states.
- Typed adapter contracts and replaceable factories for infrastructure, observability, CI/CD, secrets, AI, notifications and constrained execution.
- Read-only AWS EC2 inventory and CloudWatch helpers; Prometheus/Grafana adapters; Jenkins/GitHub run observation and signed event ingestion; scoped/revocable outbound Linux diagnostics.
- Deduplicated incidents, bounded multi-step AI planner, masked local dotenv OpenAI configuration, configurable model/output features, six immutable read-only diagnostic handlers, scoped/freshness-aware source correlation, strict evidence validation and explicit missing/insufficient evidence. Compatible providers retain the existing abstraction. No AI output can authorize execution.
- Canonical hashed action plans, explicit human decisions, scope/permission/expiry/precondition revalidation, transactional one-time consumption, sandbox execution, independent target verification, uncertainty recording and read-only reconciliation. Production-changing handlers are unsupported.
- Durable reports with timezone-aware windows, data coverage, incident/deployment/action outcomes, scheduled generation, independent SMTP delivery and bounded retry/failure records. Safe cancellation of unstarted jobs and stalled-job recovery.
- Docker development stack; optional Prometheus/Grafana/Alertmanager/OTel Collector/Loki/Tempo profile with datasource/dashboard provisioning, scrape and alert rules; optional Terraform IAM discovery role.
- Architecture, threat/security model, API/adapter guides, setup, deployment, IAM, connector, AI/webhook/report configuration, backup/restore and troubleshooting documentation.

## Actual verification

| Check | Result |
|---|---|
| PostgreSQL backend suite | **119 passed** (49 existing + 70 new AI/planner checks), no skips; real local PostgreSQL, separate `atlasops_test` database |
| Approval negative/security checks | Passed: no approval, rejection, expiry, changed plan/target/operation, unauthorized or cross-tenant decision, unsafe parameters, concurrent duplicate use, current membership, changed preconditions, failed verification, uncertain results and reconciliation |
| OpenAI / compatible AI | **Mocked HTTP only**: structured output, explicit format/token capabilities, missing credentials, 401/403, 429, network timeout, malformed/oversized/truncated output, refusal, fabricated references, prompt injection, exact credential destination and secret masking passed. **No live OpenAI call was made.** |
| Investigation planner | Five synthetic API/job/PostgreSQL scenarios passed: API failure, database timeout, deployment regression, incomplete telemetry and inconclusive/conflicting evidence. Iteration/tool/deadline/evidence/window/output bounds, repeated queries, current tenant/environment/resource permissions, registry reads, interrupted-job no-retry behavior and unchanged approval/hash/sandbox invariants passed. |
| OIDC checks | RSA signature, issuer, audience and expiry validated with a generated test signing key; live identity provider not configured |
| Migration checks | Initial upgrade, downgrade-to-base/upgrade roundtrip on the expendable test database, and schema-drift check passed |
| Browser tests | **2 passed** against actual API, worker, scheduler, PostgreSQL and Redis: full synthetic alert → evidence-only investigation → proposal → confirmed approval → verified execution → report; tablet navigation. Planner budget/coverage UI is checked. Each run uses an isolated synthetic tenant, and evidence-only mode prevents paid/model calls even if a real key is configured. |
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
3. **Investigation:** bounded multi-step planner, immutable read-only registry, OpenAI-compatible transport, model capability configuration, source correlation, output/reference validation and no-provider behavior are implemented and verified with mocked HTTP plus synthetic records. A live key/model/quota/capability acceptance call, external raw trace/log retrieval, service-dependency graph analysis and real root-cause accuracy remain unverified. Evidence-only collection is not an AI diagnosis.
4. **Approval/constrained execution:** sandbox gate met, including mandatory negative tests. No production mutation capability is enabled or advertised.
5. **CI/CD/reporting:** local contract/scheduling/SMTP gate met. External Jenkins/GitHub API/webhook delivery and production SMTP acceptance remain unverified.
6. **Hardening/pilot:** local pilot, monitoring profile, documentation and test gates completed. Production rollout is outstanding.

## Explicit limitations

- At the start of the OpenAI extension, `OPENAI_API_KEY` and `ATLAS_AI_MODEL` were unset in both process/local dotenv configuration. No actual key was requested, printed or written. Existing `.env` contents were preserved. All new OpenAI verification is mocked; live OpenAI authentication, quota, selected-model capability compatibility and diagnosis quality require a private key/model and an explicit incident investigation. Other external AWS/CI/CD/SMTP/OIDC limits remain as documented.
- UI user administration, connector enrollment/rotation screens, full OIDC redirect/PKCE login, advanced service/dependency views and larger environment/service catalog pagination are not implemented; documented authenticated API/CLI workflows exist where stated.
- Monitoring coverage remains conservatively partial/UNKNOWN or DEGRADED. No complete historical coverage, service-health proof, SLO evaluation, trend prediction or incident resolution is inferred from no alerts or a successful handler response.
- Database RLS, dedicated deployment IAM/database roles, externally retained immutable audit storage, automatic retention/deletion, HA/failover, object storage and restore drills require production engineering and operator configuration.
- OTel API instrumentation is installed and the optional collector/Tempo pipeline runs; an application exporter/worker spans and log shipping are not fully wired. Monitoring readiness is not proof of trace/log ingestion.
- Jenkins/Alertmanager require the documented signing relay; native unsigned webhooks are rejected. GitHub's unsigned delivery timestamp limitation is documented.
- SMTP acknowledgement loss can produce duplicate email after retry; deterministic Message-ID does not guarantee exactly-once SMTP delivery.
- Reports are retained snapshots for a window/scope; regenerating an existing window returns that snapshot. Current-day snapshots are necessarily partial.
- Docker images are pinned for reproducibility; review base-image advisories and the operational patch policy before exposing any service outside a pilot network.
- The initial pilot was published to Git `main` after onboarding. Cloud publication and fresh-task restoration remain separate operations and are not implied by source commits or saved drafts. The cloud draft now preserves existing network presets and adds only `api.openai.com` plus OpenAI startup guidance; this is a saved draft, not a claim of applied runtime egress/publication.

## Exact next implementation task

Enter `OPENAI_API_KEY` and an operator-selected `ATLAS_AI_MODEL` privately in the ignored local `.env`, select the documented model capabilities, apply the cloud hostname allowance if using this cloud instance, restart API/worker, and request an authorized incident investigation with AI enabled. Record the actual live result separately from the mocked tests. See [exact OpenAI setup and troubleshooting](openai.md). Production OIDC/PKCE and external integration/pilot-hardening work remain separate; production-changing handlers stay disabled.

## OpenAI extension files and validation

Configuration: `.env.example`, `scripts/dev_env.py`, `atlasops/config.py`. Provider transport/capabilities: `adapters/ai.py`, `adapters/http.py`, `adapters/contracts.py`. Domain orchestration: `ai_schemas.py`, `investigation.py`, `diagnostics.py`, `privacy.py`; worker/API wiring in `jobs.py`, `api.py`, `schemas.py` and non-secret status in `main.py`. Current membership refresh is explicit in `auth.py`. The approval/execution implementation and canonical plan-hash code in `actions.py` were not changed. Frontend types/incident view expose opt-out, coverage and counters. New tests live in `test_ai.py` and `test_investigation.py`; test credentials are synthetic, and backend/browser suites cannot accidentally use a developer's real key.

Executed for this change: full pytest suite (**119 passed**, no skips), TypeScript typecheck, Vite production build, both Playwright browser cases (**2 passed**), Ruff lint/format, Prettier checks for changed frontend files, Git whitespace checks, and Alembic schema-drift check (**no new migration required**). Existing migrations' expendable-database upgrade/downgrade test remains in the passing suite. No new runtime dependency or lockfile change was needed. Existing upstream Starlette and Zod comment-annotation warnings remain non-failing.
