# Threat model

## Scope and trust

The attacker can control retrieved document text and a proposed JSON tool call, replay an issued capability, change a proposed payload or destination, and race execution attempts. The attacker cannot change trusted host authentication, gateway source code, the signing key, the SQLite database, policy provisioning, or source classification. The operator grants a task session an explicit record scope and action budget.

`Principal`, `put_resource`, `set_policy` and `open_session` are trusted application interfaces, not model-callable tools. A real integration must establish these from an authenticated server-side context. A caller who can construct arbitrary principals in the same trusted process is outside the boundary; hiding a Python method is not a security barrier.

## Controls and tests

| Threat | Enforcement | Regression coverage |
|---|---|---|
| Model requests a shell or forged role | Fixed versioned tool set and exact JSON keys | Unknown tool, extra identity fields, invalid schema |
| Another tenant's record or artifact | Principal/session ownership and explicit scoped IDs | Cross-tenant scope creation, reads, sessions and tokens |
| Exfiltration to an attacker account at a permitted domain | Exact scheme/host/path, tenant-bound account and fixed operation | Wrong account, malformed URL, credentials, IP destinations, query, fragment and alternate operation |
| Restricted source encoded or paraphrased | Gateway-owned union of source labels, independent of payload text | Base64 payload, harmless-looking text after mixed context, forged public label |
| Read source later relabeled public | Record version/classification captured on first read; changed source invalidates prepare | Restricted-to-public downgrade and re-read remain blocked |
| Approved effect changes | Canonical action digest includes identity, task, tool, arguments, source versions, policy version and payload hash | Payload mutation, changed source or policy |
| Stolen/replayed authority | HMAC, audience, identity, session, short TTL and durable nonce | Tampered signature, wrong signer/audience/session/tenant, expiry, replay and reconnect |
| Expiry while waiting for transaction | Freshness checked again after acquiring write lock | Injected-clock expiry regression |
| Duplicate concurrent effect | SQLite `BEGIN IMMEDIATE`, unique preview/nonce and atomic consumption/effect | Two independent connections race; one local effect |
| Partial local failure | Local effect, consumption, budget and execution audit commit together | Database trigger failure rolls back outbox; valid retry succeeds |
| Raw data leaked by evidence | Bounded, fixed outcome reports; hash-only execution audit | Synthetic secret, token and principal absent from audit export |

Classification alone never grants access: a record labeled public still requires the correct tenant and task scope. This sample has no declassification tool. Reading a changed source again does not clear older context; start a fresh, isolated task session with fresh model context after an operator reviews the change.

## Capability semantics

This is a compact application-specific HMAC envelope, not a JWT implementation or standard identity protocol. A random nonce is registered in SQLite. Claims bind the gateway audience, caller, tenant, session, preview, canonical action digest, policy revision, issue time and expiry. Default lifetime is 60 seconds; maximum 120 seconds. Previews expire after 300 seconds. One preview can mint one capability; an expired or consumed approval requires a fresh preview and, for release, a new approval.

The same trusted signing key must be retained securely for pending tokens to work across a real process restart. The demo generates a random ephemeral key and deletes its temporary database. A real service needs protected key storage, rotation/revocation design, trusted clock behavior and separate issuer/worker boundaries. A key holder can mint claims; durable issuance lookup and policy checks add constraints, but they do not make a compromised issuer safe.

## Explicit non-guarantees

1. **No prompt-injection detector.** Malicious instructions remain text. This gateway restricts permitted structured effects; it does not determine whether prose is true, benign or useful.
2. **No network or OS isolation.** No outbound request occurs. There is no DNS, redirect, TLS, proxy, container or VM enforcement. Those controls must be designed before real transport is added.
3. **No complete information-flow system.** All session reads contaminate derived artifacts conservatively, which can overblock. The host must isolate model context across sessions. Data already in a prompt, pasted from another session, emitted through an unmediated model answer or introduced by a compromised tool is not automatically tracked.
4. **No exactly-once remote delivery.** Transactional SQLite outbox creation is local. A remote adapter requires provider-side idempotency, bounded retries, delivery state and reconciliation after ambiguous timeouts.
5. **No production identity or approval UI.** The separate approver is a trusted fixture. A production UI must show the exact payload and destination from the gateway preview, validate the authenticated approver, and bind confirmation to the preview ID/digest. Approval can still be mistaken.
6. **No encrypted or immutable storage.** Source bodies, previews and artifacts are plaintext inside the temporary database; the execution audit can be rewritten by an operator. Hashes can reveal equality and should not be treated as anonymization. Public demo evidence omits these raw records and hashes.
7. **No denial-of-service service guarantee.** Proposals, payloads, scope and per-session executions are bounded. This local library does not provide network rate limiting, session creation quotas, preview retention, multi-host coordination or database migration support.
8. **No full denial audit.** Successful executions are recorded transactionally. Production requires privacy-preserving denial events, retention, monitoring and alerting. The demo's fixed decision traces are evidence, not a monitoring service.

An approved public artifact can still contain offensive, inaccurate or unwanted public text. Account/permission enforcement is not content moderation. Adding a text classifier would not replace the controls above.

## Deployment gate before real data

Keep this sample offline until identity, protected issuer keys, tool/process isolation, source labeling, exact approval UI, encrypted storage, retention/deletion, transport allowlisting/account verification, downstream idempotency and monitoring have explicit owners and tests. These are integration requirements, not completed controls in this repository.
