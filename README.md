# Applied AI Engineering

Three independent, runnable reference projects for turning operational requirements into inspectable AI workflows. Each includes source code, fictional fixtures, reproducible checks, recorded evidence, and an explanation of its boundaries.

| Project | Operational problem | Implementation |
|---|---|---|
| [Object Evidence](object-evidence/README.md) | Keep storage-backed retrieval traceable when documents change, disappear, or fail to synchronize | Python, bounded B2/S3-compatible reads, atomic incremental index, content hashes, exact citations, optional LangChain bridge and local-model quote validation |
| [Staffing Workbench](staffing-agent/README.md) | Recover a search workflow after interruption while keeping scope and approval outside a model's authority | TypeScript, eligibility-filtered retrieval, SQLite checkpoints, validated tool proposals, lease fencing, bounded retries, human approval and a simulated outbox |
| [Agent Capability Gateway](agent-capability-gateway/README.md) | Keep an agent's executed action bound to its authorized tenant, task, payload and destination account | Python standard library, expiring HMAC capabilities, gateway-owned provenance, policy revocation and durable single-use SQLite execution |

These are independent samples, not commissioned employer work or official provider integrations. All included documents and profiles are fictional. There are no real candidates, patient records, private application materials, account credentials, or external outreach actions.

## Run the offline examples

The default workflows require no service accounts, model service, package installation, or API keys.

### Object Evidence — Python 3.12+

From the repository root:

```sh
cd object-evidence
python -m object_evidence demo
python -m object_evidence evaluate
python -m unittest discover -s tests -v
```

Use `py -3.12` on Windows or `python3` where appropriate. The [walkthrough](object-evidence/docs/WALKTHROUGH.md) covers source changes, failure recovery, citations, and adaptation to another document corpus.

### Staffing Workbench — Node 24.19.x

From the repository root:

```sh
cd staffing-agent
node --test tests/*.test.ts
node scripts/evaluate.ts
node scripts/demo.ts
```

The demo exercises an actual child-process interruption, persisted recovery, retry, approval, and an idempotent simulated outbox. It regenerates fictional evidence files and removes its temporary databases. The [adaptation guide](staffing-agent/docs/CUSTOMIZATION_AND_INTERVIEW.md) maps new business needs to implementation changes and acceptance checks.

### Agent Capability Gateway — Python 3.12+

From the repository root:

```sh
cd agent-capability-gateway
python demo.py
python verify.py
```

The gateway executes real local policy checks around untrusted tool proposals. It checks the destination account even when the hostname is allowed, binds approval to the exact payload, rejects replay across concurrent database connections, and preserves restricted source labels through encoded or rewritten text within a tracked session. The only release effect is a local outbox row; no network request or model call occurs. The [walkthrough and customization guide](agent-capability-gateway/CUSTOMIZATION.md) explains how to adapt the boundary without claiming a general prompt-injection defense.

## Inspect the evidence

Recorded during October 22, 2026 in Mexico City (some UTC timestamps fall on October 23); these are bounded engineering checks, not production outcome claims.

| Evidence | Observed result | Scope |
|---|---|---|
| [Object tests](object-evidence/evidence/tests.json) | 60 passed; 3 explicitly skipped on the Windows verification host | 63 discovered; optional LangChain, POSIX FIFO, and symlink availability are reported separately |
| [Object evaluation](object-evidence/evidence/evaluation.json) | 8/8 retrieval cases and 7/7 synchronization/deletion checks | Handwritten, in-sample fictional documents |
| [Object package check](object-evidence/evidence/package-smoke.json) | Packaged fixture resources and isolated demo/evaluation passed | Locally built wheel, not a published package |
| [Staffing execution](staffing-agent/evidence/demo.json) | 20 tests passed, persisted restart and approval checks passed | Single-host SQLite reference; no external delivery |
| [Staffing evaluation](staffing-agent/evidence/evaluation.json) | 8/8 scenarios; BM25 and lexical fusion both MRR 1.0 | Small synthetic set; no measured ranking uplift |
| [Gateway tests](agent-capability-gateway/evidence/tests.json) | 36/36 passed; zero skipped on the Windows verification host | Tenant/account scope, payload mutation, expiry, revocation, concurrent replay, source relabeling and atomic rollback |
| [Gateway execution](agent-capability-gateway/evidence/demo.json) | 10/10 scenarios; two permitted, eight denied, one local outbox effect | Real Python/SQLite policy execution with fictional identities and simulated egress; zero model/network calls |
| Local model checks: [objects](object-evidence/evidence/local-model.json), [staffing](staffing-agent/evidence/live-model.json) | Two successful local Qwen3 smoke cases for each project | Exact-quote validation or constrained tool proposals; not a model benchmark |

CI runs offline behavior and fixture checks. Workflow actions are pinned to commit SHAs. CI does not invoke Ollama, use cloud credentials, or send recruiting messages. Hosted runner results are separate from the checked-in local evidence.

## How the AI integration is controlled

- Object Evidence treats retrieved documents as data. The optional model selects a citation and an exact quote; deterministic validation rejects invented quotations or references outside the supplied context.
- Staffing Workbench validates a single allowed tool proposal against the approved request. Tenant scope comes from the trusted backend principal contract, not model output. Approval is a separate transaction.
- Agent Capability Gateway keeps permission checks outside a model. It binds canonical action digests to short-lived single-use capabilities, then rechecks identity, scope, source versions and current policy inside the execution transaction. [Research notes](agent-capability-gateway/RESEARCH.md) explain the account-binding and provenance decisions, including counterevidence and tradeoffs.
- Change a company's source, schema, workflow, or model through explicit interfaces, then add representative success and failure cases before claiming improvement. The project guides explain those extension points.

## Boundaries

Live B2 service verification, learned-embedding quality, representative held-out evaluation, production scale, and actual recruiting outcomes have not been established. The staffing principal is a local fixture: a deployment needs real authentication and server-derived tenant identity. A browser selector is not authorization. Scores are retrieval signals, not hiring or clinical competence decisions.

Local-model adapters require explicit opt-in and an already installed operator-controlled model. A loopback URL alone cannot establish how a separately configured model server executes requests. Read the project threat models before providing private data or adding an external connector.

The gateway assumes trusted host authentication, code, signing keys and database access. It is not an OS/network sandbox, a complete information-flow system, a prompt-injection detector or a remote exactly-once delivery service. Its approval identities are fixtures and its execution audit records successful local operations only. Cross-session model context and unmediated outputs require additional controls. See its [threat model](agent-capability-gateway/THREAT_MODEL.md) before integrating it with real tools.

## Development and license

Developed with AI-assisted coding tools, with implementation review, failure-path tests, and recorded verification. The code, measurements, limitations, and decisions are available for inspection rather than presented as unverified claims of autonomous or production performance.

MIT licensed. See [LICENSE](LICENSE) and the preserved project-level license notices.
