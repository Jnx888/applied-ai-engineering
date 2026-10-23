# Architecture decisions

## 001 — Single-host durable reference over a framework demo

Use Node 24 native TypeScript stripping and SQLite WAL without package dependencies. This makes the recovery and transaction behavior inspectable and runnable without cloud accounts. Native stripping is execution, not type checking. A production build should add a pinned compiler/linter and data migrations. Move to a durable queue/PostgreSQL or workflow engine when multi-host scheduling, partitioning or measured contention warrants it; preserve the same idempotency and tenant invariants.

## 002 — Model proposes; code controls

The default planner is deterministic. The optional real Ollama planner produces a schema-constrained lookup proposal from a structured approved request. It cannot invent another tool or alter scope. This limited use establishes an integration boundary without pretending the model adds intelligence to a simple form. A future free-form brief parser should produce a reviewable proposed request and obtain user confirmation before this workflow starts.

## 003 — Transparent retrieval baseline first

BM25, lexical cosine and RRF are deterministic and inspectable. Lexical vectors are not learned embeddings. On eight curated fixtures, BM25 and fusion tie; there is no demonstrated uplift. Keep the simpler baseline available. The optional embedding reranker is wired to a real local API and mock-tested, but no learned embedding experiment is reported. Reverse the default only after independently labeled queries demonstrate improved recall/ranking without eligibility violations or unacceptable latency/cost.

## 004 — Internal draft and human approval

The workflow produces an internal review draft, not a hiring recommendation or candidate message. There is no recipient or external sender. Human approval records the transition to a simulated outbox atomically. Adding external delivery requires recipient/consent verification, provider-side idempotency, cancellation semantics and uncertain-delivery recovery tests.

## 005 — Evidence has narrow claims

Real unit/integration tests and local-model runs are labeled separately from mock protocol tests and browser demonstrations. Synthetic ranking labels are declared in advance in `data/scenarios.json`, but are intentionally easy smoke fixtures. Relevance, fairness, business impact and production scale remain unmeasured. Negative results such as a tied baseline are preserved.
