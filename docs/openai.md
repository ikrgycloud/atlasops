# OpenAI and bounded AI investigation

AtlasOps supports the OpenAI Chat Completions API through its existing provider-neutral `AIProvider` and `SafeHTTP` adapter. The same planner works with an operator-configured compatible provider. There is no hard-coded model and no OpenAI SDK dependency. AI output is an investigation result or a read-only diagnostic request; it is never an approval or executable action plan.

## Local configuration

Edit your existing **ignored** `.env` privately. Do not paste the key into chat, commit it, set a `VITE_` variable, or put it in an integration form. Add/update these entries yourself; leave unrelated credentials intact:

```dotenv
OPENAI_API_KEY=
ATLAS_AI_PROVIDER=openai
ATLAS_AI_URL=https://api.openai.com/v1
ATLAS_AI_MODEL=
ATLAS_AI_ALLOWED_HOSTS=api.openai.com
ATLAS_AI_RESPONSE_FORMAT=json_schema
ATLAS_AI_TOKEN_PARAMETER=max_completion_tokens
```

Enter your real key after `OPENAI_API_KEY=` and a model available to your OpenAI project after `ATLAS_AI_MODEL=`. The empty placeholders are intentional. `scripts/dev_env.py` adds only empty AI placeholders when creating a **new** `.env`; an existing file is preserved byte-for-byte. It never fills or overwrites a user's key. `OPENAI_API_KEY` is a Pydantic `SecretStr` loaded by the backend from the local `.env` or injected process environment, independent of the `ATLAS_` prefix. Repr/JSON serialization masks it; no endpoint returns it. It is unwrapped only for authenticated server-side requests and redaction.

With a key and model supplied, a blank URL defaults to the official endpoint. Setting `ATLAS_AI_PROVIDER=openai` binds credential use to **HTTPS, api.openai.com, port 443, path /v1**, with no userinfo/query/fragment. Redirects are rejected. The configured AI hostname allowlist defaults to the single hostname `api.openai.com`; custom compatible destinations must be explicitly allowed through `ATLAS_AI_ALLOWED_HOSTS` or the existing `ATLAS_INTEGRATION_HOSTS`. No wildcard or arbitrary destination is introduced. The application preserves TLS certificate verification and existing trusted CA/proxy configuration. A cloud egress allowlist must separately permit `api.openai.com`; an application allowlist does not override platform networking. This chat saved that single domain addition as a reviewable cloud draft, not an applied runtime update.

Restart **both API and worker** after editing configuration, from the repository root:

```bash
.venv/bin/python scripts/local_services.py restart
```

For Compose, recreate the API/worker/scheduler with the updated private env file. The frontend does not read the OpenAI key. Its configured/unavailable status is based on non-secret backend metadata, not a verified billing/authentication check.

## Choose model capabilities explicitly

| Setting | Behavior |
|---|---|
| `ATLAS_AI_RESPONSE_FORMAT=json_schema` | Requests strict JSON Schema output. The selected model must support Chat Completions `response_format.json_schema`, the generated nested schema and its constraints. All object properties, including nullable defaults, are required in the wire schema. |
| `ATLAS_AI_RESPONSE_FORMAT=json_object` | Requests JSON object mode. The selected model must support it. AtlasOps still performs full Pydantic/tool/evidence validation. |
| `ATLAS_AI_RESPONSE_FORMAT=text_json` | Omits `response_format` and asks for JSON in the prompt. Useful for a compatible provider/model lacking the two structured features. Non-JSON/markdown or schema-invalid responses fail closed. |
| `ATLAS_AI_TOKEN_PARAMETER=max_completion_tokens` | Sends the configured token ceiling under this parameter; use only with a model that supports it. |
| `ATLAS_AI_TOKEN_PARAMETER=max_tokens` | Explicit compatibility option for models/providers requiring the older parameter. |

No temperature or native tool-calling feature is assumed. The planner requests diagnostic queries as a validated JSON envelope, so a model need not support provider-specific function calling. There is no automatic model substitution, format downgrade, token-limit increase or additional retry when a provider rejects a capability. Check the selected model's current documentation and project access. A large reasoning-token allocation may consume the completion budget before producing JSON; the output-truncated failure remains visible.

For another compatible provider, keep `ATLAS_AI_PROVIDER=compatible`, set its base URL and allow its hostname explicitly. The previous `ATLAS_AI_SECRET_REF=ATLAS_SECRET_...` binding is still supported. On the official endpoint, a non-empty local `OPENAI_API_KEY` takes priority over an existing compatible-provider secret reference. If it is empty, an explicitly configured reference may supply official-endpoint authentication. The local `OPENAI_API_KEY` is **never** forwarded to a custom endpoint. Environment secret references retain their existing runtime/proxy semantics; they are not copied into prompts.

## Run a live investigation

1. Register or ingest an incident in an environment you are authorized to operate. Connect sources or collect observations so there is actual evidence to investigate.
2. Open the incident. Keep **Use configured AI provider** checked and choose **Collect & investigate**. To collect evidence without any model call, uncheck it.
3. The API creates a durable investigation/job. The separate worker collects initial context and asks the selected model to request additional registered diagnostics or return a final finding.
4. Inspect hypotheses, supporting/contradicting IDs, confidence, missing sources, coverage/freshness and the planner's iteration/query counters. `COMPLETED` means a validated model response completed; it does not mean a root cause was proven or the incident resolved.
5. Any remediation must still go through the unchanged proposal → exact canonical hash → human approval → sandbox-only execution path. AI prose claiming approval changes no approval record or authority.

The API route remains `POST /api/v1/incidents/{id}/investigations`; it now accepts optional JSON `{"use_ai": true}` (default) or `{"use_ai": false}`. Existing clients without a body continue to work. Poll the job or GET the incident's investigations. No schema migration is needed: evidence, source coverage and planner metadata use the existing structured findings column.

## Registered diagnostics and actual evidence

The immutable registry exposes only:

- `incident.read`: persisted incident context and timestamps.
- `evidence.read`: authorized stored observations, with bounded variable payloads.
- `metrics.read`: ingested metric observations, including metrics collected through configured Prometheus/AWS paths. No arbitrary model-supplied PromQL is executed.
- `deployments.read`: actual environment-level deployment records. Per-resource deployment impact is not inferred when the record has no such target metadata.
- `logs.references`: stored, authorized log references. This does not fetch arbitrary log URLs or imply external raw logs were retrieved.
- `traces.references`: stored trace/span identifiers. External trace/span payload retrieval is not implemented or fabricated.

Every request is bound by the backend to the original incident. The model cannot choose a tenant/environment/incident, arbitrary URL, SQL query, shell command or Python callable. The registry checks current user membership, environment access and resource scope at each read. The planner revalidates access before model calls and before accepting final findings. Source records outside scope are excluded; denied requests terminate the investigation. All reads have a PostgreSQL statement timeout and an audit event.

Correlation uses actual shared resource, route, deployment-revision, trace and span identifiers within the selected window. Such links are labeled shared identifiers, not proof of causation. Source coverage records the latest retained observation and missing sources. Unavailable raw logs/traces are always stated. Important conclusions must cite IDs that were actually collected; invented IDs fail validation. Confirmed/probable findings require multiple distinct references, and insufficient independent confirmation is downgraded to a hypothesis. This guard cannot prove semantic truth; human assessment remains required.

## Enforced limits

| Environment setting | Default | Hard maximum |
|---|---:|---:|
| `ATLAS_AI_MAX_ITERATIONS` | 4 | 8 |
| `ATLAS_AI_MAX_TOOL_CALLS` | 8 | 16 |
| `ATLAS_AI_MAX_QUERY_WINDOW_SECONDS` | 7200 | 7200 |
| `ATLAS_AI_MAX_EVIDENCE` | 100 | 200 |
| `ATLAS_AI_MAX_CONTEXT_BYTES` | 60000 | 128000 |
| `ATLAS_AI_MAX_OUTPUT_BYTES` | 32768 | 65536 |
| `ATLAS_AI_MAX_OUTPUT_TOKENS` | 2500 | 8000 |
| `ATLAS_AI_REQUEST_TIMEOUT_SECONDS` | 15 | 20 |
| `ATLAS_AI_MAX_ELAPSED_SECONDS` | 60 | 75 |

The tool budget includes the three initial registered reads. Each model step can request at most four queries; each query can return at most 50 records, is limited to the investigation window and at most two hours, and has a 2-second database statement timeout. Records/fields and the aggregate evidence/context are bounded; partial coverage is reported when limits apply. HTTP response bytes, decoded model content, provider token allocation, per-I/O timeouts, streamed-chunk deadline checks and between-step wall-clock deadlines are bounded. A blocking I/O may finish at its timeout boundary; no subsequent query/model step or successful finding is accepted after the deadline. The worker also retains its outer hard time limit.

Budget exhaustion returns `BUDGET_EXHAUSTED`, preserves partial evidence/coverage, supplies an insufficient-evidence finding and marks the durable job failed. A provider/validation/authorization failure is recorded as `FAILED` with a stable error code. Missing configuration/credentials or an evidence-only request returns `AI_UNAVAILABLE` while preserving useful evidence. Model failures and interrupted investigation workers are **not automatically retried**, so restart/retry cannot silently reset the per-investigation budgets or multiply paid calls. An authorized operator can explicitly start a new investigation.

## Privacy and operational handling

Only authorized, bounded incident/observation/deployment context and references are transmitted. No application settings, authentication headers, user passwords or raw credential files are included. Redaction masks credential-like fields, recognizable key/header patterns, configured OpenAI credentials and URL userinfo/query strings before sending evidence. The same validated findings are persisted without provider response bodies or credentials in error logs. Redaction is defense in depth, not a complete PII detector: review source data, restrict access, and use an OpenAI project/model/data policy appropriate to your organization. Existing ingested text can contain sensitive operational information even if credentials are redacted. Log text remains untrusted data and cannot alter the backend's registry or authorization.

The UI's default checkbox controls sending context to the configured external model. Reports/audit records retain investigation results under existing database retention/access controls. Read-only AI diagnostics do not bypass infrastructure approvals. Production-changing handlers remain disabled.

## Troubleshooting and verification scope

- `ai_model_missing` / `ai_not_configured`: set a model and provider/base URL; restart API and worker.
- `ai_credentials_missing`: enter the key locally or provide the configured compatible secret binding. Do not print it to check presence.
- `ai_authentication_failed`: provider returned 401/403. Check key/project/model access privately; provider error bodies are not echoed.
- `ai_rate_limited`: provider returned 429, which may represent rate or quota limits. Review the account privately, then explicitly retry with a new investigation when appropriate.
- `ai_request_rejected`: inspect your selected model's endpoint/output/token-parameter support. There is no automatic feature fallback.
- `destination_not_allowed` / `ai_openai_endpoint_invalid`: fix the exact allowed hostname/official endpoint. Do not disable TLS or allow arbitrary destinations.
- `ai_timeout` / `ai_unreachable`: check approved egress, DNS, trusted proxy CA and connectivity. A saved cloud network draft does not itself apply runtime access.
- `invalid_ai_output`, `unknown_evidence_reference`, `unregistered_ai_tool_call`: the response did not meet the contract; no tool/approval authority is inferred.
- `investigation_*_exhausted`: review partial coverage and choose a narrower question/window or a deliberate bounded configuration change.
- `diagnostic_access_denied` / `diagnostic_window_denied`: the query exceeded current authorization or the backend-bound window; do not bypass it.
- `investigation_interrupted`: the worker stopped mid-run. No automatic model replay is performed.

Automated tests use **mocked OpenAI HTTP**, synthetic scenarios, a real local PostgreSQL database and the actual API/job/registry code. Browser tests explicitly select evidence-only mode, so adding a real local key cannot make the suite issue paid calls. At implementation time no live OpenAI key was configured and **no live OpenAI call was performed**. Passing mocked tests does not establish your key, model access, quota, live capability compatibility or actual production root-cause accuracy. Verify the live workflow above after entering the key privately.
