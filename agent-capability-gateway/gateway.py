"""Typed action authorization and a local egress simulator. No network or LLM calls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class Denied(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_json(raw: str) -> dict:
    if not isinstance(raw, str):
        raise Denied("invalid_json_size")
    try:
        if len(raw.encode()) > 16_384:
            raise Denied("invalid_json_size")
    except UnicodeError:
        raise Denied("invalid_json") from None
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Denied("duplicate_json_key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(Denied("invalid_json_constant")))
        # Escaped unpaired surrogates are valid JSON syntax but invalid UTF-8.
        canonical(value)
    except (ValueError, RecursionError, UnicodeError):
        raise Denied("invalid_json") from None
    if not isinstance(value, dict):
        raise Denied("invalid_json_object")
    return value


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Denied("invalid_schema")


def label(value, maximum=100):
    if not isinstance(value, str) or not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise Denied("invalid_identifier")
    return value


@dataclass(frozen=True)
class Principal:
    """Host-authenticated identity. Never construct this from an agent proposal."""
    subject: str
    tenant: str
    roles: frozenset[str]


class Gateway:
    AUDIENCE = "agent-capability-gateway:v1"
    TOOLS = {"records.read.v1", "artifact.prepare.v1", "artifact.release.v1"}
    LEVELS = {"public": 0, "internal": 1, "restricted": 2}
    TOKEN_KEYS = {"v", "nonce", "preview_id", "session_id", "tenant", "subject", "audience", "action_sha256", "policy_version", "issued_at", "expires_at"}

    def __init__(self, database: str | Path, signing_key: bytes, *, clock=time.time):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise Denied("signing_key_too_short")
        self._key = signing_key
        self.clock = clock
        self.db = sqlite3.connect(database, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, active INTEGER NOT NULL);
            INSERT OR IGNORE INTO policy VALUES(1,1,1);
            CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY, tenant TEXT NOT NULL, classification TEXT NOT NULL, body TEXT NOT NULL, version TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL, task TEXT NOT NULL, scope TEXT NOT NULL, budget INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS context(session_id TEXT NOT NULL REFERENCES sessions(id), resource_id TEXT NOT NULL REFERENCES resources(id), version TEXT NOT NULL, classification TEXT NOT NULL, PRIMARY KEY(session_id,resource_id));
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), tenant TEXT NOT NULL, body TEXT NOT NULL, sha256 TEXT NOT NULL, classification TEXT NOT NULL, provenance TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS previews(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), action TEXT NOT NULL, sha256 TEXT NOT NULL, created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS capabilities(nonce TEXT PRIMARY KEY, preview_id TEXT NOT NULL UNIQUE REFERENCES previews(id), expires INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0, approver TEXT);
            CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, nonce TEXT NOT NULL UNIQUE REFERENCES capabilities(nonce), tenant TEXT NOT NULL, account TEXT NOT NULL, artifact_id TEXT NOT NULL, payload_sha256 TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at INTEGER NOT NULL, session_hash TEXT NOT NULL, action_hash TEXT NOT NULL, outcome TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def put_resource(self, resource_id: str, tenant: str, classification: str, body: str):
        """Trusted operator provisioning interface; deliberately absent from dispatch."""
        label(resource_id); label(tenant)
        if not isinstance(classification, str) or classification not in self.LEVELS or not isinstance(body, str) or len(body.encode()) > 4096:
            raise Denied("invalid_resource")
        version = digest({"classification": classification, "body": body})
        self.db.execute("INSERT INTO resources VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET tenant=excluded.tenant,classification=excluded.classification,body=excluded.body,version=excluded.version",
                        (resource_id, tenant, classification, body, version))

    def set_policy(self, *, active: bool = True):
        """Trusted operator revocation interface; no agent tool can call this."""
        self.db.execute("UPDATE policy SET version=version+1,active=? WHERE id=1", (int(active),))

    def open_session(self, principal: Principal, task: str, record_ids: list[str], *, budget=12) -> str:
        if "operator" not in principal.roles or type(budget) is not int or not 1 <= budget <= 100:
            raise Denied("session_not_authorized")
        label(principal.subject); label(principal.tenant); label(task)
        if (not isinstance(record_ids, list) or not 1 <= len(record_ids) <= 8
                or not all(isinstance(item, str) for item in record_ids) or len(set(record_ids)) != len(record_ids)):
            raise Denied("invalid_scope")
        for resource_id in record_ids:
            label(resource_id)
            row = self.db.execute("SELECT tenant FROM resources WHERE id=?", (resource_id,)).fetchone()
            if row is None or row["tenant"] != principal.tenant:
                raise Denied("resource_scope_denied")
        session_id = secrets.token_hex(16)
        self.db.execute("INSERT INTO sessions(id,tenant,subject,task,scope,budget) VALUES(?,?,?,?,?,?)",
                        (session_id, principal.tenant, principal.subject, task, canonical(record_ids).decode(), budget))
        return session_id

    def _session(self, principal, session_id):
        if "operator" not in principal.roles:
            raise Denied("operator_required")
        session = self.db.execute("SELECT * FROM sessions WHERE id=?", (label(session_id),)).fetchone()
        if session is None or session["tenant"] != principal.tenant or session["subject"] != principal.subject:
            raise Denied("session_scope_denied")
        return session

    def _resource(self, session, resource_id):
        if resource_id not in json.loads(session["scope"]):
            raise Denied("resource_scope_denied")
        row = self.db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
        if row is None or row["tenant"] != session["tenant"]:
            raise Denied("resource_scope_denied")
        return row

    def _context(self, session):
        context = list(self.db.execute("SELECT * FROM context WHERE session_id=? ORDER BY resource_id", (session["id"],)))
        if not context:
            raise Denied("source_context_required")
        for row in context:
            if self._resource(session, row["resource_id"])["version"] != row["version"]:
                raise Denied("source_changed_since_read")
        level = max(context, key=lambda row: self.LEVELS[row["classification"]])["classification"]
        return level, {row["resource_id"]: row["version"] for row in context}

    def _destination(self, tenant, value, classification):
        exact(value, {"url", "account", "operation"})
        url = value["url"]
        if not isinstance(url, str) or len(url) > 300:
            raise Denied("invalid_destination_url")
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise Denied("invalid_destination_url") from None
        if (parsed.scheme != "https" or parsed.netloc != "review.example.test" or parsed.path != "/inbox"
                or parsed.query or parsed.fragment or parsed.username or parsed.password
                or any(ord(c) < 32 for c in url) or url != "https://review.example.test/inbox"):
            raise Denied("destination_not_allowed")
        if value["operation"] != "create_review_copy":
            raise Denied("operation_not_allowed")
        if value["account"] != f"{tenant}-review":
            raise Denied("destination_account_denied")
        if classification != "public":
            raise Denied("restricted_data_flow")
        return value

    def _action(self, principal, session_id, raw):
        proposal = strict_json(raw)
        exact(proposal, {"tool", "arguments"})
        tool, args = proposal["tool"], proposal["arguments"]
        if not isinstance(tool, str) or tool not in self.TOOLS:
            raise Denied("tool_not_allowed")
        session = self._session(principal, session_id)
        policy = self.db.execute("SELECT * FROM policy WHERE id=1").fetchone()
        if not policy["active"]:
            raise Denied("policy_revoked")
        if session["used"] >= session["budget"]:
            raise Denied("action_budget_exceeded")
        resource_versions = {}
        classification = "public"
        if tool == "records.read.v1":
            exact(args, {"resource_id"})
            resource = self._resource(session, label(args["resource_id"]))
            resource_versions[resource["id"]] = resource["version"]
            classification = resource["classification"]
        elif tool == "artifact.prepare.v1":
            exact(args, {"text"})
            if not isinstance(args["text"], str) or not 1 <= len(args["text"].encode()) <= 4096:
                raise Denied("invalid_payload_size")
            classification, resource_versions = self._context(session)
        else:
            exact(args, {"artifact_id", "destination"})
            artifact = self.db.execute("SELECT * FROM artifacts WHERE id=?", (label(args["artifact_id"]),)).fetchone()
            if artifact is None or artifact["tenant"] != session["tenant"] or artifact["session_id"] != session_id:
                raise Denied("artifact_scope_denied")
            if hashlib.sha256(artifact["body"].encode()).hexdigest() != artifact["sha256"]:
                raise Denied("artifact_integrity_failed")
            resource_versions = json.loads(artifact["provenance"])
            for resource_id, version in resource_versions.items():
                if self._resource(session, resource_id)["version"] != version:
                    raise Denied("source_changed_since_prepare")
            classification = artifact["classification"]
            self._destination(session["tenant"], args["destination"], classification)
        action = {"v": 1, "session_id": session_id, "subject": principal.subject, "tenant": principal.tenant,
                  "task": session["task"], "tool": tool, "arguments": args, "policy_version": policy["version"],
                  "classification": classification, "resource_versions": resource_versions}
        if tool == "artifact.release.v1":
            action["payload_sha256"] = artifact["sha256"]
        return action

    def preview(self, principal: Principal, session_id: str, raw: str) -> dict:
        action = self._action(principal, session_id, raw)
        preview_id = secrets.token_hex(16)
        action_hash = digest(action)
        self.db.execute("INSERT INTO previews VALUES(?,?,?,?,?)", (preview_id, session_id, canonical(action).decode(), action_hash, int(self.clock())))
        result = {"preview_id": preview_id, "action_sha256": action_hash,
                "approval_required": action["tool"] == "artifact.release.v1", "action": action,
                "effect": "local_simulated_outbox_only" if action["tool"] == "artifact.release.v1" else "local_read_or_artifact"}
        if result["approval_required"]:
            result["payload_preview"] = self.db.execute("SELECT body FROM artifacts WHERE id=?", (action["arguments"]["artifact_id"],)).fetchone()[0]
        return result

    def authorize(self, principal: Principal, session_id: str, preview_id: str, *, approver: Principal | None = None, ttl=60) -> str:
        self._session(principal, session_id)
        if type(ttl) is not int or not 1 <= ttl <= 120:
            raise Denied("invalid_capability_ttl")
        row = self.db.execute("SELECT * FROM previews WHERE id=? AND session_id=?", (label(preview_id), session_id)).fetchone()
        if row is None:
            raise Denied("preview_not_found")
        action = json.loads(row["action"])
        now = int(self.clock())
        if now - row["created"] > 300 or now < row["created"]:
            raise Denied("preview_expired")
        current = self._action(principal, session_id, canonical({"tool": action["tool"], "arguments": action["arguments"]}).decode())
        if digest(current) != row["sha256"]:
            raise Denied("preview_changed")
        if action["tool"] == "artifact.release.v1":
            if approver is None or "approver" not in approver.roles or approver.tenant != principal.tenant or approver.subject == principal.subject:
                raise Denied("independent_approval_required")
        nonce = secrets.token_hex(24)
        claims = {"v": 1, "nonce": nonce, "preview_id": preview_id, "session_id": session_id,
                  "tenant": principal.tenant, "subject": principal.subject, "audience": self.AUDIENCE,
                  "action_sha256": row["sha256"], "policy_version": action["policy_version"], "issued_at": now, "expires_at": now + ttl}
        try:
            self.db.execute("INSERT INTO capabilities(nonce,preview_id,expires,approver) VALUES(?,?,?,?)",
                            (nonce, preview_id, now + ttl, approver.subject if approver else None))
        except sqlite3.IntegrityError:
            raise Denied("preview_already_authorized") from None
        encoded = base64.urlsafe_b64encode(canonical(claims)).decode().rstrip("=")
        signature = hmac.new(self._key, encoded.encode(), hashlib.sha256).hexdigest()
        return encoded + "." + signature

    def _claims(self, token):
        if not isinstance(token, str) or len(token) > 4096:
            raise Denied("invalid_capability")
        try:
            encoded, signature = token.split(".")
            if not signature.isascii():
                raise Denied("invalid_capability")
            expected = hmac.new(self._key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise Denied("invalid_capability_signature")
            claims = strict_json(base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True).decode())
        except (ValueError, UnicodeError):
            raise Denied("invalid_capability") from None
        exact(claims, self.TOKEN_KEYS)
        if claims["audience"] != self.AUDIENCE or type(claims["v"]) is not int or claims["v"] != 1:
            raise Denied("capability_audience_denied")
        if any(not isinstance(claims[key], str) or not 1 <= len(claims[key]) <= 100
               for key in ("nonce", "preview_id", "session_id", "tenant", "subject", "action_sha256")):
            raise Denied("invalid_capability")
        if type(claims["policy_version"]) is not int or claims["policy_version"] < 1:
            raise Denied("invalid_capability")
        now = int(self.clock())
        if type(claims["expires_at"]) is not int or type(claims["issued_at"]) is not int:
            raise Denied("invalid_capability")
        if claims["issued_at"] > now or claims["expires_at"] <= now or not 0 < claims["expires_at"] - claims["issued_at"] <= 120:
            raise Denied("capability_expired")
        return claims

    def execute(self, principal: Principal, session_id: str, token: str, raw: str) -> dict:
        claims = self._claims(token)
        if (claims["session_id"] != session_id or claims["tenant"] != principal.tenant or claims["subject"] != principal.subject):
            raise Denied("capability_scope_denied")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            # Lock contention must not allow a token that expired while waiting.
            self._claims(token)
            stored = self.db.execute("SELECT * FROM capabilities WHERE nonce=?", (claims["nonce"],)).fetchone()
            if stored is None or stored["preview_id"] != claims["preview_id"] or stored["expires"] != claims["expires_at"]:
                raise Denied("capability_not_issued")
            if stored["consumed"]:
                raise Denied("capability_replayed")
            action = self._action(principal, session_id, raw)
            if digest(action) != claims["action_sha256"] or action["policy_version"] != claims["policy_version"]:
                raise Denied("approved_action_changed")
            result = self._effect(action, claims["nonce"])
            self.db.execute("UPDATE capabilities SET consumed=1 WHERE nonce=?", (claims["nonce"],))
            self.db.execute("UPDATE sessions SET used=used+1 WHERE id=?", (session_id,))
            self.db.execute("INSERT INTO events(at,session_hash,action_hash,outcome) VALUES(?,?,?,?)",
                            (int(self.clock()), hashlib.sha256(session_id.encode()).hexdigest(), claims["action_sha256"], "executed_local"))
            self.db.execute("COMMIT")
            return result
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _effect(self, action, nonce):
        args, session_id = action["arguments"], action["session_id"]
        if action["tool"] == "records.read.v1":
            row = self.db.execute("SELECT * FROM resources WHERE id=?", (args["resource_id"],)).fetchone()
            self.db.execute("INSERT OR IGNORE INTO context VALUES(?,?,?,?)", (session_id, row["id"], row["version"], row["classification"]))
            return {"kind": "record", "resource_id": row["id"], "text": row["body"], "classification": row["classification"], "version": row["version"]}
        if action["tool"] == "artifact.prepare.v1":
            artifact_id = secrets.token_hex(16)
            payload_hash = hashlib.sha256(args["text"].encode()).hexdigest()
            self.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)", (artifact_id, session_id, action["tenant"], args["text"], payload_hash, action["classification"], canonical(action["resource_versions"]).decode()))
            return {"kind": "artifact", "artifact_id": artifact_id, "payload_sha256": payload_hash, "classification": action["classification"]}
        artifact = self.db.execute("SELECT * FROM artifacts WHERE id=?", (args["artifact_id"],)).fetchone()
        effect_id = secrets.token_hex(16)
        self.db.execute("INSERT INTO outbox VALUES(?,?,?,?,?,?,?)", (effect_id, nonce, action["tenant"], args["destination"]["account"], artifact["id"], artifact["sha256"], artifact["body"]))
        return {"kind": "local_simulated_outbox", "effect_id": effect_id, "payload_sha256": artifact["sha256"], "account": args["destination"]["account"], "network_calls": 0}

    def audit_export(self) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT id,at,session_hash,action_hash,outcome FROM events ORDER BY id")]

    def effect_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]


def proposal(tool: str, **arguments) -> str:
    return canonical({"tool": tool, "arguments": arguments}).decode()
