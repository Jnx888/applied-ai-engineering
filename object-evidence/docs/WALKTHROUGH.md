# Explain, run and adapt the project

## Five-minute walkthrough

**Problem, 30 seconds.** “An object-storage corpus changes over time. An AI assistant needs to know where a passage came from, when evidence became stale, and what to do when a document disappears. I built an independent integration sample to make those decisions explicit.”

**Build, 60 seconds.** Run `python -m object_evidence demo`. Show the six fixture objects, deterministic generation, and repeated sync with six reused objects/zero fetches. Point to `Source` in `sources.py`: the same index can consume a local directory or the optional B2 list/get adapter.

**Evidence, 60 seconds.** Show `questions[0].matches[0]`: exact text, source key, SHA-256, line range and citation ID. Explain that this is deterministic retrieval and not an LLM-written answer. Then show `evidence/local-model.json`: a real local Qwen3 call selected a quote, and separate code verified both its citation and exact text membership.

**Failure, 60 seconds.** Run `python -m object_evidence evaluate`. Show corruption causing a failed sync with the previous snapshot preserved. Default queries reject stale state. After the source is repaired, a deleted document is removed from active retrieval and replaced with a content-free tombstone.

**Engineering judgment, 60 seconds.** Open the tests for incomplete pagination, fake network failure, prefix/path scope, changed ETag, fabricated model quote and concurrent writer. State which checks were skipped on this host. Explain that live B2 verification and broader retrieval quality remain unmeasured.

**Adaptation, 30 seconds.** Pick a real use case: internal technical docs, support runbooks or archive discovery. Discuss data classification, source scope, required freshness, corpus size and access rules before choosing embeddings or a model. Do not describe this sample as work done for an employer.

## Code map

| Need | Starting point | Required acceptance check |
|---|---|---|
| New object provider | `sources.py` / `Source`, `B2Source` | Full list completion, prefix/namespace isolation, conditional read, bounded failure; never reuse B2 endpoint validation for an arbitrary provider |
| Customer-specific corpus | `LocalSource`, config, private index | Dedicated namespace/state, representative document types, no secrets in public fixtures |
| Better chunking | `engine.py` / `chunks` | Reconstruct exact line spans and invalidate citation IDs on content changes |
| Semantic retrieval | `engine.py` / `query` or LangChain bridge | Compare held-out hit@k/MRR, latency and cost against the lexical baseline; preserve authorization and provenance |
| Model selection/prompting | `ollama_extractor.py` / `SYSTEM`, `extract` | Unsupported answers abstain; unknown IDs/edited quotations rejected; tests remain separate from live provider runs |
| More complete answers | Separate generator after retrieval | Add faithfulness/relevance evaluation and source validation; never weaken quote validation silently |
| Production workflow | Separate service/queue around core | Server-side authorization, tenant isolation, secret storage, audit/retention/restore procedures; current local app is not sufficient |
| Evaluation changes | `object_evidence/fixtures/evaluation.json` | Add unseen questions and negative cases before tuning; report failures and original dataset versions |

## A useful customization exercise

1. Start with an authorized, non-sensitive operations corpus. Define the questions it should answer and identify the expected source for each.
2. Configure one storage prefix and private local state. Keep environment secrets out of both source control and the generated site.
3. Add six held-out questions: two paraphrases, one no-answer request, one stale policy, one deletion and one malicious instruction. Freeze those before changing retrieval.
4. Run the baseline, inspect misses, then improve one variable: chunking, term normalization, an embedding provider or model selection.
5. Keep a before/after table with actual counts and failure examples. Do not convert tiny fixture scores into production accuracy claims.

## What to be ready to explain in an interview

- Why an ETag is a change hint rather than a SHA-256 guarantee.
- Why incomplete listing must never look like mass deletion.
- Why a deleted document can survive in backups even after the active index removes it.
- Why a citation does not replace authorization.
- Why a schema-conforming model answer can still be wrong, and why exact quoting verifies a narrower property.
- How a local reproducible baseline reduces setup friction for an open-source integration reviewer.
- Which parts you understand and can modify yourself. Practice a small live change, run its tests, and describe its tradeoff; don't claim skills solely because this sample exists.
