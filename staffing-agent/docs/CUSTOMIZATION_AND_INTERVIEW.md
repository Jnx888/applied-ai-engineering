# Adapt the reference to a company's need

Use this project to demonstrate how a requirement changes code, policy and evidence together. Do not imply it was commissioned by a company or operated on real users.

| Need | Concrete extension | Acceptance test |
|---|---|---|
| A different staffing specialty | Add job-relevant fields at ingest, extend `SearchRequest`, `scopedProfiles` and tool schema; require explicit user-approved values | Unsupported/missing eligibility fields fail closed; other-tenant records never reach scores or embedding inputs |
| Plain-English staffing briefs | Add structured model extraction before `submit`; display the proposed fields and require confirmation | Ambiguous requirements abstain/ask for missing fields; injected role/tenant/tool changes are rejected; no workflow submission until confirmation |
| Semantic discovery | Select an approved local embedding model, run the actual adapter, collect independent relevance judgments, compare against BM25 | Measure recall@k, MRR/nDCG, abstention, eligibility violations, latency and cost on held-out queries; report ties/regressions |
| Multi-tenant production app | Connect a verified identity provider; derive server-side Principal; move data access behind an authenticated API | Forged body tenant/roles do not change scope; cross-tenant job IDs are unreadable, unapprovable and uncancellable |
| Operational scale | Replace SQLite queue with a measured durable service when contention justifies it; preserve the state machine contract | Process crash/replay, stale-worker fencing, duplicated delivery events and atomic outbox invariants still pass |
| Profile revocation | Persist permission/eligibility version and recheck before review/approval; invalidate cached search results | Revoked profiles cannot be approved from an older draft; audit records identify the policy version without storing unnecessary personal data |
| Actual notifications | Add a separately authorized delivery connector with verified destinations and provider idempotency | Crash after provider acceptance but before checkpoint does not duplicate delivery; cancellation and uncertain delivery are reconciled |

## A concise demo sequence

1. Select the ICU night scenario. Explain that hard filters run first, then BM25/lexical fusion. Show the partial ACLS match and its coverage rather than claiming every result is fully qualified.
2. Change state to NY or query to oncology chemotherapy and show abstention. Switch the fictional tenant and show that the other tenant's records are never scored.
3. Open recorded SQLite evidence: child process exited after committing its lease; the restarted worker reclaimed it after expiry. Approval, not search completion, inserted the simulated outbox item exactly once.
4. Open actual local-model evidence: two schema-constrained proposals from `qwen3:4b-instruct`, exact server validation, no outbox entry. The model proposes a lookup; it does not control tenant identity or delivery.
5. Show the baseline comparison: both methods score equally on easy fixtures. Propose a held-out relevance study instead of claiming semantic uplift.

## Interview explanations

**Why a model for such a constrained task?** The model path is a bounded integration example; it is not necessary to execute a structured form. This makes the control boundary testable. The next useful model feature would be confirmed extraction from ambiguous briefs, with its own evaluation dataset.

**What survives a crash?** The committed request, attempt count, lease and events survive in SQLite. An expired lease is reclaimable. The old lease token cannot commit. The simulated outbox and completed state share a transaction.

**What does this not prove?** Production scale, real recruiting impact, clinical credential validity, hiring fairness, distributed exactly-once delivery, a deployed identity layer or learned semantic ranking quality. Those are separate validation projects.

**How would you tailor it?** Start with the company's failure mode: scope leakage, irrelevant search, recovery gaps or slow approval. Change the smallest module, add a counterexample before changing behavior, preserve the baseline, then measure the relevant outcome.

Present the work as an AI-assisted reference implementation you can explain, run and extend. Do not use it as evidence of undisclosed client delivery or production employment history.
