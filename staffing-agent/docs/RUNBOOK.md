# Runbook

1. Use Node 24.19.x. Run `node --test tests/*.test.ts`; all tests must pass. The child-process crash test exits its fixture with code 17 intentionally and asserts that observation.
2. Run `node scripts/evaluate.ts` and inspect scenario-level scores, abstention and eligibility. Changing labels to fit results is not an improvement.
3. Run `node scripts/demo.ts` to regenerate safe evidence. It verifies the suite, then records real persisted recovery and approval traces. The demo removes only its uniquely created OS temporary directory.
4. Optional model verification requires an operator-controlled local Ollama service and a locally installed model. Run the explicit command in README. If the first case fails or times out, the script stops; inspect local service health before trying again. Do not download models automatically.
5. `evidence/live-model.json` records two real structured planning calls from October 22, 2026. Do not present old results as a new run. No embedding run is included.

## Failure handling

- `retry`: wait until `nextAt`; a polling worker should schedule from the durable timestamp. Reference demo advances a test clock rather than sleeping.
- `running` after worker crash: wait for the lease to expire; another worker can claim it. Never forcibly mark completed.
- `failed`: inspect non-sensitive transition code and replay only after a deliberate operator decision using a new idempotency key. There is no hidden automatic infinite retry.
- `awaiting_approval`: review source citations and gaps. A role other than approver must be rejected; other-tenant IDs return `not_found`.
- `cancelled`: no commit or outbox insertion is possible; an in-flight model request may still finish.
- Model transport failures, including interrupted streams, are retryable; malformed/oversized output and altered scope are terminal.

## Persistence and operations boundary

SQLite is local, single-host durable storage. The tests verify committed-state recovery across a terminated process and reconnection, not disk loss, distributed failover or power-loss durability on every storage system. For a real deployment: back up with a consistent SQLite backup mechanism, test restore to a separate environment, protect files and WAL files, add retention/deletion, and measure locking/queue latency. Do not naively copy only the main DB while WAL writes are active.

Monitor transition counts, retry age, expired leases, failed jobs, approval backlog and denied authorization attempts. The project includes inspectable durable transition events; it does not install an external monitoring/alerting system. Record latency/cost from real traffic only after consent and privacy decisions.

The source is dependency-free but still relies on Node/SQLite/Ollama when enabled. Keep runtime versions supported and review upstream advisories. No package installation is needed to reproduce the checked-in reference.
