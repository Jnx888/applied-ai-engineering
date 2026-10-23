"""Run actual local policy scenarios and emit public-safe evidence."""

import argparse
import base64
import json
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fixtures import APPROVER, DESTINATION, OPERATOR, OTHER, prepared, run_action, seed
from gateway import Denied, Gateway, proposal


def run_demo():
    with tempfile.TemporaryDirectory(prefix="agent-gateway-demo-") as temp:
        now = [int(datetime.now(timezone.utc).timestamp())]
        gateway = Gateway(Path(temp) / "gateway.sqlite", secrets.token_bytes(32), clock=lambda: now[0])
        try:
            seed(gateway)
            rows = []
            def record(case_id, title, expected, action, *, trace):
                before = gateway.effect_count()
                try:
                    result = action()
                    actual = "allowed"
                except Denied as error:
                    actual = error.code
                    result = None
                after = gateway.effect_count()
                rows.append({"id": case_id, "label": title, "expected": expected, "actual": actual,
                             "passed": actual == expected, "decision": "allowed" if actual == "allowed" else "denied",
                             "outbox_effect_delta": after - before, "trace": trace,
                             "effect_kind": result.get("kind") if result else None})

            session = gateway.open_session(OPERATOR, "read-public-guide", ["public-runbook"])
            record("read", "Read an explicitly scoped record", "allowed",
                   lambda: run_action(gateway, session, proposal("records.read.v1", resource_id="public-runbook")),
                   trace=["Use trusted operator and tenant", "Check record against session scope", "Verify single-use capability", "Return fictional source data"])

            session, artifact, release = prepared(gateway)
            preview = gateway.preview(OPERATOR, session, release)
            record("approval", "Require a separate approver for release", "independent_approval_required",
                   lambda: gateway.authorize(OPERATOR, session, preview["preview_id"]),
                   trace=["Preview exact tool, payload digest and destination account", "No independent approver provided", "Deny capability issuance"])
            token = gateway.authorize(OPERATOR, session, preview["preview_id"], approver=APPROVER)
            record("release", "Release the exact approved public artifact", "allowed",
                   lambda: gateway.execute(OPERATOR, session, token, release),
                   trace=["Verify HMAC, expiry, identity and policy", "Compare current action with approved digest", "Consume nonce and create one local outbox row atomically"])
            record("replay", "Reject a replay of the same approval", "capability_replayed",
                   lambda: gateway.execute(OPERATOR, session, token, release),
                   trace=["Receive the same signed envelope again", "Observe consumed nonce", "Keep outbox count unchanged"])

            session, artifact, release = prepared(gateway)
            destination_attack = proposal("artifact.release.v1", artifact_id=artifact["artifact_id"], destination={**DESTINATION, "account": "attacker-account"})
            record("account", "Block attacker account on an approved domain", "destination_account_denied",
                   lambda: gateway.preview(OPERATOR, session, destination_attack),
                   trace=["Hostname and path match approved service", "Account differs from tenant-bound destination", "Deny before issuing any capability"])

            session = gateway.open_session(OPERATOR, "read-public-guide", ["public-runbook"])
            record("tenant", "Reject another tenant's public-classified record", "resource_scope_denied",
                   lambda: gateway.preview(OPERATOR, session, proposal("records.read.v1", resource_id="other-tenant")),
                   trace=["Check authenticated tenant and task record scope", "Record belongs to another tenant", "Reject regardless of public classification"])

            encoded = base64.b64encode(b"DEMO_SECRET_ASTER_42").decode()
            session, artifact, release = prepared(gateway, restricted=True, text=encoded)
            record("provenance", "Keep restricted classification after encoding", "restricted_data_flow",
                   lambda: gateway.preview(OPERATOR, session, release),
                   trace=["Read restricted fictional context", "Prepare encoded text with gateway-owned inherited label", "Deny restricted context at the public review sink"])

            session, artifact, release = prepared(gateway)
            read = proposal("records.read.v1", resource_id="public-runbook")
            preview = gateway.preview(OPERATOR, session, proposal("artifact.prepare.v1", text="Approved text"))
            token = gateway.authorize(OPERATOR, session, preview["preview_id"])
            record("payload", "Reject changed payload after preview", "approved_action_changed",
                   lambda: gateway.execute(OPERATOR, session, token, proposal("artifact.prepare.v1", text="Changed text")),
                   trace=["Issue envelope bound to canonical approved text", "Receive different text at execution", "Reject action digest mismatch"])

            preview = gateway.preview(OPERATOR, session, read)
            token = gateway.authorize(OPERATOR, session, preview["preview_id"], ttl=1)
            now[0] += 2
            record("expired", "Reject an expired capability", "capability_expired",
                   lambda: gateway.execute(OPERATOR, session, token, read),
                   trace=["Advance injected test clock beyond expiry", "Recheck freshness at execution", "Deny without effect"])

            preview = gateway.preview(OPERATOR, session, read)
            token = gateway.authorize(OPERATOR, session, preview["preview_id"])
            gateway.set_policy(active=False)
            record("revoked", "Recheck revoked policy at execution", "policy_revoked",
                   lambda: gateway.execute(OPERATOR, session, token, read),
                   trace=["Authorize under active policy", "Operator revokes policy", "Execution rechecks policy and stops"])

            audit = gateway.audit_export()
            report = {"schema_version": 1, "project": "Agent Capability Gateway", "generated_at": datetime.now(timezone.utc).isoformat(),
                      "execution_mode": "real_python_sqlite_policy_checks_with_local_egress_simulator",
                      "data_scope": "fictional_operator_owned_fixtures", "model_calls": 0, "network_calls": 0,
                      "scenarios": rows, "passed": sum(row["passed"] for row in rows), "total": len(rows),
                      "local_outbox_effects": gateway.effect_count(), "audit_event_count": len(audit),
                      "audit_contains_synthetic_canary": "DEMO_SECRET_ASTER_42" in json.dumps(audit),
                      "controls": ["Task/tenant/resource scope", "Destination account and operation binding", "HMAC-bound action digest", "Single-use nonce and transactional local outbox", "Expiry and policy revocation", "Gateway-owned source classification"],
                      "limits": ["Trusted host identity and separate approver are fixtures, not a deployed authentication system", "No live outbound delivery or network sandbox", "No universal prompt-injection detection claim", "Local policy scenarios are not a production security benchmark", "In-process enforcement assumes trusted gateway and tool code"]}
            return report
        finally:
            gateway.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_demo()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
