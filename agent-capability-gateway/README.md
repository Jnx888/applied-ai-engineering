# Agent Capability Gateway

An offline reference implementation that checks whether an agent's proposed tool action still matches its exact authorization **at execution time**. It demonstrates policy enforcement outside the model, including tenant and record scope, destination account binding, expiring HMAC capabilities, and durable single-use execution.

The use case is a report assistant reading fictional operations documents. An operator may read explicitly scoped records and prepare an artifact. Copying a public artifact into a designated **local review outbox** requires a different approver. Restricted context, changed payloads, attacker-controlled accounts, expired approvals, replay and revoked policy are rejected.

This is independent portfolio work. It is not a company deliverable, production security product, universal prompt-injection defense or network sandbox. No model, API key, cloud account, Docker service or package installation is required. The example makes **zero model and network calls**; `review.example.test` is a fictional destination checked as data, never contacted.

## Run it

Requires Python 3.12 or later and its standard library. From this source directory:

Windows:

```powershell
py -3.12 demo.py --output evidence/demo.json
py -3.12 -m unittest -v test_gateway.py
py -3.12 verify.py
```

macOS / Linux:

```sh
python3 demo.py --output evidence/demo.json
python3 -m unittest -v test_gateway.py
python3 verify.py
```

`verify.py` runs the actual test suite and scenarios, then writes `evidence/tests.json` and `evidence/demo.json`. Both exit nonzero on a failed check. Test databases are temporary and cleaned up; only safe outcome reports remain. Reports include source hashes so a recorded run can be compared with the code it exercised. Timestamps and measured duration change on each run.

## The boundary that matters

```text
Untrusted document/model proposal
          |
          v
Typed JSON and explicit tool allowlist
          |
Trusted principal + task + tenant + record scope
          |
Exact preview: payload, destination account, operation, source versions
          |
Separate authenticated approver for release (fixture identity in this demo)
          |
Short-lived HMAC capability bound to preview digest
          |
Recheck current policy, source versions, budget, identity and expiry
          |
SQLite transaction: consume nonce + local effect + minimal audit
```

Retrieved text is returned as data. It cannot create an admin role, grant approval, add a tool or change the gateway's policy. The gateway does not ask an LLM to decide whether another LLM's request is safe.

Three explicit tools are available:

| Tool | Allowed effect | Authority boundary |
|---|---|---|
| `records.read.v1` | Return one scoped fictional record | Same tenant, same task session, explicit record ID |
| `artifact.prepare.v1` | Store a bounded local text artifact | Inherit classification and source versions from every record read in that session |
| `artifact.release.v1` | Create one local review-outbox row | Public context, exact destination URL/account/operation, separate approver and single-use capability |

The illustrative destination is `https://review.example.test/inbox`, operation `create_review_copy`, account `<tenant>-review`. An approved hostname does not authorize another account on that hostname. Models cannot submit a `classification` or `role` field: extra fields are rejected.

## What the evidence proves

The recorded demo includes ten scenarios: a permitted read, missing approval, permitted local release, replay, wrong account, cross-tenant read, encoded restricted context, payload mutation, expiry and revocation. The suite adds concurrency, restart, transaction rollback, malformed input, provenance changes and other contract tests. See the generated reports for current counts; do not treat these fixture results as attack-detection accuracy or a production benchmark.

Two concurrent connections using the same nonce yield one local effect. The second is rejected. A simulated database failure rolls back both the outbox insertion and nonce consumption, allowing a valid retry. This is a property of the **local SQLite transaction**, not an exactly-once guarantee for a remote API.

The audit export contains successful execution IDs, time, session/action hashes and a fixed outcome. It excludes raw text, tokens and principal names. Denied scenario outcomes appear in the public demo report, but this sample does not provide comprehensive denial telemetry or immutable audit storage.

## Code map and adaptation

| File | Responsibility |
|---|---|
| `gateway.py` | Schemas, scope, provenance, preview, capability issue/verify, transaction and local effects |
| `fixtures.py` | Fictional trusted identities, source records and helper calls |
| `demo.py` | Reproducible policy scenarios and compact website evidence |
| `test_gateway.py` | Positive, adversarial and concurrency regressions |
| `verify.py` | Measured test results, scenario evidence and source hashes |
| `THREAT_MODEL.md` | Trusted assumptions, tested controls and limits |
| `CUSTOMIZATION.md` | Interview walkthrough and steps for a real integration |
| `RESEARCH.md` | Primary sources, counterevidence and design rationale |

Start with [CUSTOMIZATION.md](CUSTOMIZATION.md) to explain or adapt the code. Read [THREAT_MODEL.md](THREAT_MODEL.md) before adding a real tool. The current implementation deliberately uses a small, reviewable, fixed tool set rather than a generic plugin runner.

## Important limits

- `Principal` is a trusted-host abstraction. Fixture identities are not real authentication or proof that a human approved anything.
- Arbitrary code running as the gateway's OS user can bypass this in-process boundary. Production workers must not possess issuer keys, database access or alternate network paths.
- Context labels conservatively track reads within one gateway session. They cannot identify secret data pasted from elsewhere, cross-session model memory, implicit flows or incorrectly labeled sources.
- Keys, source data, previews and outbox payloads are held locally; SQLite is not encrypted by this sample. Use only the fictional fixtures here.
- Only the local test suite has run. No real provider, identity system, outbound transport, production load, live-user study or independent security certification is claimed.

MIT licensed. Contributions should preserve the distinction between simulated egress and real local policy execution.
