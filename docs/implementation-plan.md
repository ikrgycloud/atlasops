# AtlasOps AI implementation plan

The repository was empty (unborn local branch; the remote advertised no refs). This project is being created at the user's explicit request. Work in this checkout; no worktree is necessary.

## Milestones and acceptance gates

1. **Foundation** — Python 3.12/FastAPI, PostgreSQL/Alembic, tenant membership authorization, typed adapters, React/TypeScript, Compose, and JSON logs. Gate: migrations, authenticated requests, tenant isolation, backend tests, and frontend type/build checks.
2. **Read-only integrations** — AWS EC2/CloudWatch, Prometheus, Grafana, outbound Linux connector, alert ingestion, inventory, and integration health. Gate: queries against a configured local source, missing telemetry stays UNKNOWN; adapter contract tests. Live AWS remains unverified without credentials.
3. **Investigation** — deduplicated incidents, structured evidence, bounded AI interface, explicit uncertainty, and timeline. Gate: synthetic telemetry investigation plus invalid AI output and unsafe input tests.
4. **Approval and execution** — canonical immutable plans, permission checks, expiry, transactional single-use consumption, sandbox handlers, independent verification, and reconciliation. Gate: end-to-end flow and mandatory negative security/concurrency tests. No production mutation handlers.
5. **CI/CD and reports** — signed/idempotent webhooks, read-only Jenkins/GitHub adapters, timezone-aware daily reports, durable jobs, SMTP delivery. Gate: local webhook/API/SMTP doubles, schedule deduplication and delivery failure tests.
6. **Pilot hardening** — optional observability profile, deployment/IAM/connector/backup guides, UI integration, and complete verification report. Gate: documented local pilot, tests and static checks, honest outstanding limitations.

## Dependencies and decisions

PostgreSQL is the business-state authority. Redis/Celery only dispatch durable database jobs. API and workers run independently. Configuration comes from validated environment variables. All integration URLs are administrator-controlled and constrained by an operator allowlist. No arbitrary command, SQL, or general cloud-mutation tool is exposed. Sandbox remediation changes only a dedicated database sandbox resource. Missing paid/external credentials do not block the core workflow.

Implement complete vertical slices in the above order. Preserve user files. Update implementation-status.md with actual executed checks and limitations; distinguish test doubles from live integrations.
