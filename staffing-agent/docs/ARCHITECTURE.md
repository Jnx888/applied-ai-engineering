# Architecture and invariants

```text
Trusted authenticated-principal adapter (fixture today)
  -> validate user-approved request + tenant-scoped idempotency
  -> SQLite queued job
  -> worker transactional lease (attempt budget, fencing token)
  -> reference planner OR explicit local Ollama structured proposal
  -> exact tool/argument validation; unchanged user-approved scope
  -> tenant + availability + role + state + shift filter
  -> BM25 + lexical cosine + reciprocal rank fusion
     [optional learned embedding rerank of gated candidates]
  -> transactional result/draft checkpoint
  -> abstained OR awaiting_approval
  -> authorized human approval + simulated outbox + completed (atomic)
```

`queued -> running -> awaiting_approval -> completed` is the normal path. A lack of evidence yields `abstained`. Transient failures yield `retry` with 1s then 2s backoff; the third unsuccessful attempt becomes `failed`. Invalid tool proposals fail terminally. An operator can cancel nonterminal work. A crashed running job is reclaimable only after lease expiry. Terminalization of an exhausted lease does not hide another ready job.

The lease token protects commits from older workers after recovery. Ownership is checked before planning, after asynchronous planning, and in the final transaction. An already-started provider request may finish after cancellation; it cannot commit or create an outbox record. There is no outbound delivery worker.

Transactions use `BEGIN IMMEDIATE`, prepared SQL, a uniqueness constraint on `(tenant_id, idempotency_key)`, and a unique outbox key per job. Approval inserts the outbox row and terminal checkpoint together. A test injects a SQL trigger failure and confirms both roll back. Different requests with the same idempotency key are rejected, not silently accepted.

Search's `minScore` means minimum **lexical query coverage**, not probability, hiring confidence or cosine score. Default 0.3 allows partial matches for review. The ICU example includes the complete ICU profile plus an ACLS partial match; citations and component scores expose the difference. Change the threshold according to a validated use case, not a desired demo result.

RRF ranks the BM25 and lexical-cosine orderings. These are both lexical signals. They can tie or add no value. The embedding variant reranks only candidates that pass the same conservative lexical gate; it does not recover semantic-only matches. This trades recall for explicit evidence and keeps the optional model's scope small. It needs an independent relevance dataset before expansion.

Events record transition types, attempt numbers, result counts and controlled planner identifiers. They exclude raw prompts, profile bodies, credentials and exception stacks. The SQLite request/result tables still hold fictional application data; production would require a retention, deletion and access policy.

The browser module is a UI demonstration of the same ranking code. Shipping fictional cross-tenant records in the public bundle is intentional for demonstration. Real cross-tenant data must never be bundled into client JavaScript.
