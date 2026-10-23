# Threat model

| Threat | Enforced control | Residual boundary / acceptance check |
|---|---|---|
| Cross-tenant search or IDOR | Authenticated-principal contract; tenant-filtered SQL reads/approval/cancel/outbox; retrieval filters before scoring/provider inputs | Principal is a local fixture today. An HTTP integration must derive it from verified identity, never request JSON |
| Untrusted model tool/action | One tool allowlist, exact argument keys, unchanged approved scope, no model tenant field | Model output is data. Structured output alone is insufficient; server validation is mandatory |
| Prompt injection in profile content | No profile text enters the planner; retrieved text cannot invoke tools; drafts use source-field citations | Poisoned data can still alter ranking. Production ingestion needs source trust, schema validation, review and provenance |
| Unconsented profile use | Explicit `availableForReview === true` prefilter | Fictional flag only. Real revocation must invalidate indexes/caches and be rechecked before approval |
| Unauthorized outreach | Approver role required, atomic simulated outbox, no external sender | This is an internal review draft, never an employment decision. Real outreach needs destination verification and separate consent/approval |
| Duplicate work / stale completion | Durable lease tokens, attempt budget, idempotency uniqueness, transactional fencing | Guarantees are local to SQLite. Real external delivery needs provider idempotency plus reconciliation |
| Cancellation races | Pre-adapter, post-planner and commit ownership checks | An already-started local-model request is not force-cancelled by workflow cancellation. No resulting state change can commit |
| SQL injection | Prepared statements for all application values | Local DB/file permissions and an untrusted SQL/admin surface are outside the supplied app |
| SSRF / secret egress | Optional adapter fixes loopback origin, rejects redirects, bounds output/time, no secrets | Operator-controlled local-model configuration is necessary; a local service could itself route elsewhere |
| Resource exhaustion | Query/batch/output bounds, up to three attempts, fixed backoff, lease limit | No public API exists. Rate limiting, tenant quotas, bounded queue size and admission control are required before deployment |
| Sensitive logs | No prompts/profile bodies/raw error text in event log | Subject IDs and real data should be minimized and protected if a production audit schema is added |
| XSS in a consumer UI | Search module returns plain data | Consumer must render text, not raw HTML. Do not use `dangerouslySetInnerHTML` with profile/model content |

No PHI or protected traits are in the fixtures. Do not turn these scores into automated hiring decisions. Neither passing tests nor a small benchmark establishes fairness, credential correctness, accessibility, healthcare compliance or safety. The project implements engineering boundaries; deployment governance requires separate review.

No hosting, real authentication, secret manager, backup service, alert system, payment flow or external email connector is included. Their absence is explicit, rather than simulated by a UI label.
