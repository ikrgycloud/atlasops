# Architecture

React + React Router + TanStack Query calls the versioned FastAPI API. Authentication resolves a persisted user and tenant membership; environment scope and explicit permissions constrain application services. Services own database transactions. PostgreSQL stores operational records, immutable action plans, approval decisions, audit events, reports, and durable jobs. Alembic owns schema changes.

The worker dispatches durable jobs using Redis/Celery, with database claims and reconciliation after uncertain execution. AI investigation receives read-only evidence and emits validated structured findings; it has no execution capability. A separate execution service rechecks authorization, immutable plan hashes, expiry, scope, current policy, and single-use approvals before calling a constrained sandbox handler and independently checking the outcome.

External adapters implement typed capability interfaces. AWS discovery uses read-only EC2/CloudWatch calls. Prometheus supplies metrics; Grafana supplies metadata. CI/CD adapters observe runs, while signed webhooks normalize deployments. The outbound Linux connector has scoped, revocable machine authentication and accepts no arbitrary commands. SMTP delivery is independent of durable report generation.

The initial deployment is a modular monolith with independently runnable API, worker, scheduler, connector, and web processes. Optional Compose observability is a single-node development stack, not an HA design. Provider extension does not change the incident or approval domain.
