# Threat model

| Boundary / asset | Attack | Mitigation | Residual risk |
|---|---|---|---|
| Browser → API, tenant records | Forged token, IDOR, role escalation | JWT validation, persisted membership, environment filters, bounded schemas | Compromised identity provider or administrator |
| AI / telemetry → investigation | Prompt injection, fabricated approval | Evidence-as-data, strict outputs/references, no mutation tools, independent approval engine | Misleading but schema-valid hypotheses need human assessment |
| Approval → worker | Altered plan, target substitution, replay, race | Canonical hash, expiry, row lock, consumed approval, current authorization check | Database operator compromise |
| Worker → target | Timeout after submission, duplicate change | Single-use claim, no blind retry, independent verification/reconciliation | Unsupported real-world mutation handlers remain disabled |
| Integration → private network | SSRF, credential exfiltration | Operator hostname allowlist, no redirects, TLS, credentials only by validated reference | Allowed endpoint itself could be compromised; network egress controls required |
| Webhook → queue | Spoofing, replay, oversized input | HMAC, bounded body, stable idempotency key, freshness where provider supports it | GitHub does not sign a delivery timestamp; first-use delay cannot be cryptographically detected |
| Connector → control plane | Stolen machine token, cross-scope telemetry | High-entropy bearer over TLS, hash storage, scoped enrollment, revocation/rotation | Host compromise; mTLS recommended at ingress |
| Reports / logs | Sensitive data leakage | Source references, no request bodies or secret values in logs, JSON events | Source telemetry may already contain sensitive information |
| Database / broker | Data loss, job loss | PostgreSQL durable jobs, recovery sweep, backups, Redis not authority | HA, external audit retention and disaster recovery require operator deployment work |

Roles: authenticated engineers, malicious tenants, compromised connectors/integrations, external attackers, and privileged operators. Assets: credentials, infrastructure state, approvals, operational records, tenant isolation, evidence integrity and availability. Production deployment requires TLS ingress, managed identities, a secret manager, least-privilege database/runtime roles, restricted egress, monitoring, and tested backups.
