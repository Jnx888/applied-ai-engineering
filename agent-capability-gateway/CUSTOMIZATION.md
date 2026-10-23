# Explain and adapt the gateway

## A five-minute interview walkthrough

1. **Problem, 30 seconds:** an agent may read a malicious document and propose a different action from the one a user intended. Prompt wording alone should not grant authority. This example keeps authorization in ordinary application code.
2. **Allowed workflow, 60 seconds:** run `python demo.py`. Explain the public record read, prepared artifact, exact payload/destination preview, separate approver fixture and one local outbox row. Point out that a useful allowed path exists.
3. **Distinctive attack, 60 seconds:** show the `account` scenario. The host is still allowed, but the destination account is attacker-controlled. `_destination` checks the account and operation as well as the URL.
4. **Race and integrity, 60 seconds:** inspect `test_concurrent_connections_consume_once` and `test_atomic_rollback_retains_unconsumed_capability`. The capability digest is rechecked before execution; nonce consumption and the local effect share one SQLite transaction.
5. **Limits, 60 seconds:** explain why a local outbox is not real remote delivery, fixture principals are not authentication, and Python code in the same process is not a sandbox. The gateway is useful only when the host makes it the enforced path to tools.
6. **Adaptation, 30 seconds:** describe the tool-specific manifest, account mapping, classification and downstream idempotency that a real workflow would require. Use measured local evidence; do not claim production attack prevention or employer adoption.

A concise explanation you can adapt after understanding the code: “I built a deterministic gateway for agent tool proposals. It binds approval to the exact task, tenant, resource versions, payload and destination account, then rechecks those facts at execution. The offline regression suite tests changed payloads, replay and concurrent attempts. The current effect is a local SQLite outbox, so real transport and authentication remain integration work.”

## Integration contract

The untrusted proposer provides only this shape:

```json
{"tool":"records.read.v1","arguments":{"resource_id":"public-runbook"}}
```

The trusted application supplies `Principal`, `session_id`, scope and policy. Never parse those from a model's claim of identity. For each step:

```python
preview = gateway.preview(principal, session_id, raw_proposal)
# For release, a trusted UI displays preview["payload_preview"] and the
# actual action/destination, then resolves a separately authenticated reviewer.
token = gateway.authorize(principal, session_id, preview["preview_id"],
                          approver=authenticated_reviewer)
result = gateway.execute(principal, session_id, token, raw_proposal)
```

For permitted reads/prepare, `approver` can be omitted. Release requires a different same-tenant principal with the approver role. The sample has no approval website; passing `APPROVER` in fixtures is a deterministic test of the contract, not evidence of a human click.

## Adapting to a storage assistant

- Map read-only storage object IDs to tenant-scoped resource records in trusted code. Use immutable version IDs and hashes. Do not allow the proposer to supply arbitrary URLs or filesystem paths.
- Inherit provenance from the actual objects supplied to the task. An integration with Object Evidence could use its object identities/hashes as resource versions, but the two projects are intentionally uncoupled today.
- Replace the fictional destination mapping with an operator-configured account and bucket/prefix. Verify the remote account identity, scoped credentials and immutable operation. A hostname allowlist is insufficient.
- Start with a review outbox or proposed manifest. For a real write, use a separate restricted executor and provider idempotency/reconciliation. Keep delete, public ACL and permission-changing tools absent until explicitly designed.

## Adapting to a business workflow

- For a staffing or support assistant, bind source records and approval to the authenticated tenant and workflow instance.
- Define a narrow operation such as `create_internal_review_draft`, not an unrestricted `send_message` or generic HTTP client.
- Keep regulated or private context out of public sinks regardless of model-generated wording. Explicit declassification would be a new trusted human workflow, not an extra field the model may set.
- Reuse the existing business workflow for task planning; use this gateway for exact action authority and replay protection. Avoid duplicating the planner or rebuilding an identity provider.

## Changing policy safely

| Change | Edit | Required regression |
|---|---|---|
| Add a tool | `Gateway.TOOLS`, `_action`, `_effect` | Unknown fields, unauthorized operation, limits, correct effect and rollback |
| Change destination | `_destination` and trusted configuration | Same hostname/wrong account, redirects/query/credentials, changed approved destination |
| Change source class | `put_resource`, `LEVELS`, context policy | No downgrade of already-read context, mixed context and source change |
| Change identity provider | Host integration around `Principal` | Forged role/tenant, revoked identity, real approver separation |
| Add network delivery | Separate transport worker | Provider identity, TLS, redirects, egress restriction, timeout ambiguity and downstream duplicate delivery |
| Add a local or hosted model | Proposer only; feed results into `preview` | Malformed JSON, malicious retrieved text, model-supplied identity, cross-session context isolation |

A model integration is not necessary to verify the gateway's decision rules. If one is added, record model/version and which proposals it actually generated. Never let the model choose policy, issue capabilities, hold the HMAC key, or make an alternate network call around the gateway.

## Release checklist for this reference

Run `python verify.py`; compare the recorded source hashes; inspect public evidence for raw payloads or local paths; preserve limitations; keep fixture identities and example domains clearly fictional. CI definitions are reproducible instructions until a specific workflow run has actually completed. A green suite proves those cases under that runtime, not all possible adversarial behavior.
