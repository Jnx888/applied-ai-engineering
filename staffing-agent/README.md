# Staffing Workbench

A working reference for tenant-scoped staffing search and durable, human-approved AI workflows. The problem: turn a staffing request into an explainable internal review draft, while keeping eligibility rules, authorization, recovery and delivery decisions outside a model's authority.

All profiles are fictional. There are no names, contact details, patient information or real recruiting actions. This is an independent portfolio project, not work delivered to an employer.

## Run locally

Requires **Node 24.19.x**. There are no npm runtime or development dependencies and no install step.

```sh
node --test tests/*.test.ts
node scripts/evaluate.ts
node scripts/demo.ts
```

The demo creates a temporary SQLite database, runs the tests, deliberately terminates a child worker after its durable claim, restarts work after lease expiry, and verifies that approval inserts only one simulated outbox item. It also injects a transient dependency failure, checks scheduled backoff, and recovers. Temporary databases are removed. Re-running writes the latest non-sensitive evidence JSON; copy evidence to a versioned location when comparing releases.

Optional, explicit local-model check using an **already installed local-only model**:

```sh
node scripts/ollama-check.ts --allow-local-model --model qwen3:4b-instruct
```

This sends two fictional requests to loopback Ollama, with one 60-second limit per request and no retry batch. It does not download models. Check your Ollama configuration and installed model before running: a local endpoint and model-name guard alone cannot prove the server never routes to a remote provider. No embedding model is invoked by this command.

## What is implemented and what is measured

| Capability | Implementation and evidence |
|---|---|
| Search | Exact tenant, review-availability, role, state and shift filters **before** corpus statistics or provider input; BM25 plus lexical term-frequency cosine, fused by reciprocal rank |
| Explainability | Visible matched profile IDs, source-field citations, query coverage and component scores; no fabricated free-form rationale |
| Tool control | One allowlisted tool; exact-key schema validation; model cannot change approved request scope or supply a tenant ID |
| Durable execution | SQLite WAL, transactional checkpoints, unique tenant/idempotency keys, lease tokens, bounded retries, stale-worker fencing, cancellation |
| Human review | An approver role is required for the atomic completed-state/outbox transaction; outbox is simulated and has no recipient or sender |
| Actual local model | `qwen3:4b-instruct` executed two structured planning smoke cases on October 22, 2026; both passed and left the outbox empty. See `evidence/live-model.json` |
| Optional embeddings | Real `/api/embed` adapter and retrieval integration exist; mock protocol and isolation tests pass. **No learned embedding model or relevance improvement was validated.** |
| Reliability tests | Process death/restart, two SQLite connections, stale leases, cancellation before/during planning, atomic rollback, bounded backoff and malicious tool proposals |
| Retrieval evaluation | Eight curated synthetic cases; five answerable. BM25 and hybrid both score MRR 1.0; no measured uplift. Abstention matches all eight labels; no hard-filter violations |

The deterministic reference planner is the default. It is intentionally **not an LLM**. The local model is constrained to constructing a tool proposal from an already structured, user-approved request. This demonstrates model integration and enforcement; it does not demonstrate unrestricted natural-language staffing interpretation or autonomous recruiting.

## Repository map

- `src/search.ts`: browser-portable retrieval and optional embedding rerank.
- `src/planner.ts`: reference planner, tool contract and validation.
- `src/workflow.ts`: durable state machine and trusted-principal authorization boundary.
- `src/ollama.ts`: explicit opt-in, bounded local model adapter.
- `data/`: fictional profiles and declared expected relevance/abstention labels.
- `tests/`: regression and adversarial tests; real process crash fixture.
- `scripts/`: reproducible demo, evaluation and optional local model check.
- `evidence/`: safe, generated results with dates, actual scores and limitations.
- `docs/`: architecture, threat model, operational runbook and adaptation/interview guide.

The website runs `searchProfiles` against bundled fictional records. It shows recorded SQLite/model evidence; it does not run SQLite or a model in the visitor's browser. Browser tenant selection is a simulation, not an access-control guarantee.

## Boundaries

The backend accepts a **trusted Principal**, supplied here by local fixtures. There is no HTTP server, identity provider, credential store, real candidate ingestion or external delivery connector. A deployment must integrate authentication and derive tenant/roles from verified server-side identity. Do not accept these fields from a browser. Review availability is a synthetic flag, not a real consent system or credential verification.

This is a single-host reference, not scale, fairness, compliance, clinical suitability or production availability certification. References and code have been tested locally; employer adoption and business outcomes are not claimed. See `docs/THREAT_MODEL.md` and `docs/RUNBOOK.md` before extending.

## Primary implementation references

- [Node 24 SQLite API](https://nodejs.org/docs/latest-v24.x/api/sqlite.html): synchronous SQLite bindings and prepared statements.
- [Node TypeScript execution](https://nodejs.org/docs/latest-v24.x/api/typescript.html): native erasable-type support; no type-checker is bundled here.
- [Ollama chat API](https://docs.ollama.com/api/chat): JSON-schema structured output.
- [Ollama embedding API](https://docs.ollama.com/api/embed): batch embeddings with truncation disabled.

Documentation consulted October 22, 2026. The checked-in code and runtime tests, rather than a documentation version claim, establish current local compatibility.
