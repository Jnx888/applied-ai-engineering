"""Fictional operator-owned configuration. Never load identities from model output."""

from gateway import Gateway, Principal, proposal

OPERATOR = Principal("demo-operator", "tenant-a", frozenset({"operator"}))
APPROVER = Principal("demo-reviewer", "tenant-a", frozenset({"approver"}))
OTHER = Principal("demo-other", "tenant-b", frozenset({"operator", "approver"}))
DESTINATION = {"url": "https://review.example.test/inbox", "account": "tenant-a-review", "operation": "create_review_copy"}


def seed(gateway: Gateway):
    gateway.put_resource("public-runbook", "tenant-a", "public", "Fictional Aster guide: verify a restore checksum before using recovered data.")
    gateway.put_resource("restricted-note", "tenant-a", "restricted", "Fictional restricted canary: DEMO_SECRET_ASTER_42. This is not a real credential.")
    gateway.put_resource("other-tenant", "tenant-b", "public", "Fictional other-tenant document. Public classification does not grant cross-tenant access.")


def run_action(gateway, session, raw, *, approver=None):
    preview = gateway.preview(OPERATOR, session, raw)
    token = gateway.authorize(OPERATOR, session, preview["preview_id"], approver=approver)
    return gateway.execute(OPERATOR, session, token, raw)


def prepared(gateway, *, restricted=False, text="Public restore summary: verify the checksum."):
    resource = "restricted-note" if restricted else "public-runbook"
    session = gateway.open_session(OPERATOR, "prepare-review", [resource])
    run_action(gateway, session, proposal("records.read.v1", resource_id=resource))
    artifact = run_action(gateway, session, proposal("artifact.prepare.v1", text=text))
    release = proposal("artifact.release.v1", artifact_id=artifact["artifact_id"], destination=DESTINATION)
    return session, artifact, release
