# API contracts

FastAPI generates the authoritative request/response schemas at `/openapi.json` and interactive documentation at `/docs`. All operational endpoints use `/api/v1`, bearer authentication and current tenant membership, except the development token endpoint, signed webhooks and machine-authenticated connector ingestion. Liveness/readiness and metrics are separate routes.

Errors use `{ "error": { "code": "...", "message": "..." } }`. Validation errors list invalid field paths and deliberately omit input values. Missing and unauthorized scoped object IDs return 404. Permission denials return 403; missing/invalid credentials return 401. Stable adapter error codes do not contain credentials or provider response bodies.

List endpoints return `{items,total,limit,offset}`. Incident, approval, proposal, deployment, report and audit lists accept bounded `limit` (1–100) and `offset`. Incident lists accept severity/status filters. Environment/service registries currently return the initial 25 records; integration lists return 100. Paginated environment/service catalogs beyond the pilot limit are a documented extension.

| Group | Routes |
|---|---|
| Identity | POST `/auth/dev-token` (opt-in development only); GET `/me` |
| Environments | GET/POST `/environments`; GET `/environments/{id}`; GET `/environments/{id}/resources` |
| Services | GET/POST `/services`; GET `/services/{id}` |
| Incidents | GET/POST `/incidents`; GET `/incidents/{id}`; GET `/incidents/{id}/events`; POST `/incidents/{id}/status` |
| Investigation | POST/GET `/incidents/{id}/investigations`; POST `/diagnostics/query` |
| Proposals | POST `/incidents/{id}/proposals`; GET `/action-proposals`; GET `/action-proposals/{id}` |
| Approval | GET `/approvals`; POST `/approvals/{id}/decision` with decision and exact plan hash |
| Execution | POST `/action-proposals/{id}/execute`; POST `/action-proposals/{id}/reconcile` |
| Jobs | GET `/jobs/{id}`; POST `/jobs/{id}/cancel` (requester, pending/retry only) |
| Deployments | GET `/deployments`; GET `/deployments/{id}` |
| Reports | GET `/reports`; GET `/reports/daily`; GET `/reports/{id}`; POST `/reports/generate` |
| Integrations | GET/POST `/integrations`; POST `/integrations/{id}/test`; POST `/integrations/webhooks/{provider}?integration_id=UUID` |
| Connector | GET/POST `/connectors`; POST `/connectors/{id}/rotate`; POST `/connectors/{id}/revoke`; POST `/connectors/observations` |
| Audit | GET `/audit-events` (administrator permission) |
| Synthetic pilot | GET `/sandbox/resources`; POST `/sandbox/scenario` |

Investigation, report generation and execution return HTTP 202 plus a durable `job_id`. A 202 response means accepted, not completed. Poll the job or relevant records. Decisions are explicit `APPROVE` or `REJECT` bound to a SHA-256 plan hash. Approval does not implicitly issue an execution request. No endpoint accepts an arbitrary command.

Resource records are the latest authorized observations for up to 100 resource identities, with source/time/quality and normalized variable data. They are not a complete inventory if a provider query was bounded or data is missing.

Investigation creation accepts optional `{"use_ai": true}` (default) or `{"use_ai": false}` for evidence-only collection. Findings include `planner`, `sources`, `correlations`, `diagnostic_queries`, `evidence_partial` and a stable `error_code`. `BUDGET_EXHAUSTED` and provider failures are explicit non-success outcomes; a completed model response need not establish a root cause. `/me` exposes only non-secret `ai_status` configuration metadata. `/diagnostics/query` accepts only registered read-only tool names with strict, scoped query arguments. See [OpenAI investigation](openai.md).
