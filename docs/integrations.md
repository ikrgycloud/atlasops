# Configuration and integrations

All runtime settings use the `ATLAS_` prefix; `.env.example` lists them. The API validates settings at startup. Secret references must match `ATLAS_SECRET_[A-Z0-9_]+`; references resolve from the server's injected environment, never from request values, frontend bundles or database-stored credential values. Use a managed secret injector in production. Rotating a binding and restarting API/workers changes future adapter calls. Stored integration metadata never contains raw credentials.

`ATLAS_INTEGRATION_HOSTS` is an exact hostname allowlist, without schemes or paths. HTTPS is required; local HTTP additionally requires development mode and `ATLAS_ALLOW_INSECURE_INTEGRATIONS=true`. Requests do not follow redirects, use bounded timeouts and cap responses at 1 MiB. Also enforce destination/IP restrictions at the deployment egress proxy to address DNS rebinding and compromised allowed endpoints. Keep the hostname allowlist small. Private services are not prohibited if explicitly authorized by the operator.

## Implemented adapter capabilities

| Provider | Implemented operations | Authentication / scope | Verification |
|---|---|---|---|
| AWS | EC2 instance inventory, CloudWatch CPU statistics and dimension-filtered metric alarms | boto3 credential chain; workload role recommended; explicit instance IDs for discovery | SDK Stubber tests; no live account configured |
| Prometheus | Bounded instant-vector queries, normalized observations | Optional bearer secret reference, operator-allowed base URL | Local HTTP contract and actual managed Prometheus |
| Grafana | Health and dashboard metadata | Optional bearer reference | Actual local Grafana health/provisioning |
| GitHub Actions | Latest 100 run records and signed workflow_run ingestion | Repository scope, optional fine-grained read token; webhook signing reference | Local HTTP double and signed fixture tests |
| Jenkins | Last build for up to 100 jobs, signed relay event ingestion | Optional username/token reference | Local HTTP double; relay fixture contract |
| SMTP | Text report delivery with STARTTLS and deterministic Message-ID | Optional username/secret reference; destination allowlist | Local SMTP server and failure/retry tests |
| Compatible AI | Structured investigation findings; no mutation tools | Configurable HTTPS base URL/model, optional bearer reference | Output/schema/security tests; live model unconfigured |
| Linux connector | CPU load, memory, disk, configured systemd status, log **references** | Outbound high-entropy scoped bearer credential over TLS | API replay/scope/rotation/revocation tests; local Linux diagnostics |
| Sandbox execution | `sandbox.recover` only | Exact plan-bound human approval and current RBAC | PostgreSQL concurrency and end-to-end browser tests |

Capabilities are explicit and unsupported operations return an error. There are no Azure, Kubernetes mutation, arbitrary SSH, shell, Python execution, or deployment-trigger handlers. The AWS adapter's CloudWatch helpers are read-only; the automatic integration probe initially ingests EC2 inventory. CI/CD run records are workflow events; a successful workflow is not automatically proof of successful deployment or service recovery.

## AWS IAM

Use an existing workload identity/assumed role with only `ec2:DescribeInstances`, `cloudwatch:GetMetricStatistics`, and `cloudwatch:DescribeAlarms` in the selected region. These read APIs require `Resource: "*"`; constrain region/account at IAM and supply explicit instance scope in the environment registration. Do not grant administrator permissions or `RunInstances`, `RebootInstances`, deployment, scaling, or configuration mutation permissions. `infra/terraform` optionally creates this discovery role; review its plan and apply separately. No Terraform apply was performed during implementation.

## CI/CD and Alertmanager webhooks

Register the integration with its environment and a signing-key reference. POST to `/api/v1/integrations/webhooks/{provider}?integration_id=UUID`.

GitHub: subscribe to `workflow_run`, set your repository and webhook secret, use native `X-Hub-Signature-256` HMAC-SHA256. AtlasOps checks the signed repository and workflow `updated_at`, bounds freshness to five minutes and records a digest of the **signed body**. Changing the unsigned delivery ID does not defeat replay protection. GitHub has no signed delivery timestamp; first-use delays cannot be cryptographically detected, and delayed delivery outside the freshness window must be investigated/reconciled rather than silently accepted. Read access to the Git repository does not imply GitHub API access.

Jenkins and Alertmanager have no universal native webhook-signing standard. Use a trusted relay that emits `X-Atlas-Timestamp` (Unix seconds), `X-Atlas-Event-Id`, and `X-Atlas-Signature: sha256=HEX`, where HEX is HMAC-SHA256 of `timestamp + '.' + event_id + '.' + raw_body`. Freshness is five minutes. Never expose unsigned ingestion. The optional Alertmanager profile deliberately uses a local-only receiver until a relay is configured.

Alertmanager bodies follow its `alerts` list format, with labels, annotations.summary, fingerprint and generatorURL; batches are bounded to 100. Jenkins relay bodies contain `name` and `build: {number,status,timestamp,url,revision,repository,branch}`; timestamp is epoch milliseconds. GitHub consumes its workflow_run object. Body receipt is durable/idempotent before the normalization worker runs. Repeated alert fingerprints update an existing incident and reopen resolved/closed incidents. A source's resolved alert is not independent proof of service recovery.

## Investigation and AI

Set `ATLAS_AI_URL` to an operator-allowed OpenAI-compatible base URL, `ATLAS_AI_MODEL` to a model selected by the operator, and optionally `ATLAS_AI_SECRET_REF` to an injected secret name. The request uses `/chat/completions` and JSON-schema output. No model name or credential is hard-coded. Live provider compatibility must be verified for your selected model.

The diagnostic registry exposes only `evidence.read`: an authorized incident, timezone-aware window of at most two hours, at most 50 records, and an audit entry. No execution capability is available to the model. Findings validate evidence IDs, classification, confidence, hypotheses and missing evidence. A probable/confirmed claim requires multiple existing evidence references, but schema validation does not prove a root cause; humans must assess the supporting and contradicting data. External text cannot approve an action. Without AI, evidence collection completes with `AI_UNAVAILABLE` and explicit uncertainty.

Current correlation is bounded by tenant/environment/time; a complete service dependency graph, deep trace fetching, autonomous multi-step queries, historical risk prediction and SLO policy configuration remain future work. Raw logs and customer request bodies are not ingested into the operational database.

## Linux connector

An administrator creates an on-premises environment with resource scope and enrolls `/api/v1/connectors`. The server returns an enrollment token **once**; it stores only SHA-256. Store the new token in the host's secret manager or private runtime environment. Configure `ATLAS_CONNECTOR_URL`, `ATLAS_CONNECTOR_TOKEN`, `ATLAS_CONNECTOR_RESOURCE`, and a private writable `ATLAS_CONNECTOR_STATE` path. Run `connectors/linux/connector.py` with Python 3.12 and httpx. Use a dedicated unprivileged OS user, a service manager and TLS ingress. mTLS at ingress adds host certificate assurance.

Optional local settings: `ATLAS_CONNECTOR_DISK`, comma-separated allowlisted `.service` units in `ATLAS_CONNECTOR_SERVICES`, and administrator-controlled log paths in `ATLAS_CONNECTOR_LOG_PATHS`. No remotely supplied command is executed. The connector invokes only fixed `systemctl is-active -- UNIT` with validated locally configured units, and never accepts jobs from the control plane. Log payload retrieval and mutation jobs are deliberately unsupported; only references are sent. It persists an increasing sequence before sending, and the server rejects stale (over two minutes), replayed, wrong-resource, rotated or revoked observations. Rotation invalidates the prior token immediately; reset sequence state for the new identity. A missed heartbeat is visible after 120 seconds.

## Reports and email

`ATLAS_REPORT_TIMEZONE` defaults to Asia/Kolkata. `ATLAS_REPORT_HOUR` defaults to 08:00 local. Celery beat dispatches one previous-day report per tenant/window with a stable key. DST boundaries are calculated with zoneinfo, not fixed 24-hour arithmetic. Manual report generation uses the selected day or the previous operational day. A report is a persisted snapshot for that window/scope; generating it again returns that snapshot, rather than rewriting history. Generate a current-day snapshot only when you understand its partial window.

Set SMTP host, port, STARTTLS, sender, recipient, username and password reference using environment settings. Production requires STARTTLS. Only tenant-wide reports can be emailed to the shared configured recipient, preventing scoped user data from being sent to a broader audience. Email jobs retry up to four times with exponential backoff/jitter, while report data remains available. SMTP delivery is at-least-once after an acknowledgement-loss/crash; Message-ID aids downstream deduplication but SMTP cannot guarantee exactly-once delivery.
