"""An atomic local index with explicit freshness and deterministic citations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .errors import EvidenceError
from .sources import Limits, Source, check_objects

STOP_WORDS = frozenset("a an and are as at be by can do for from how i in is it of on or our the this to was we what when which with".split())


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def tokens(text: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9]+", text.lower()) if term not in STOP_WORDS and len(term) > 1]


def chunks(key: str, doc: dict, namespace: str) -> list[dict]:
    """Bounded line-based chunks retain exact source line numbers."""
    lines = doc["text"].splitlines()
    result = []
    for start in range(0, len(lines), 8):
        text = "\n".join(lines[start:start + 8])
        if not text.strip():
            continue
        end = min(start + 8, len(lines))
        identity = {"source": namespace, "key": key, "sha256": doc["sha256"],
                    "start_line": start + 1, "end_line": end}
        result.append({"citation_id": "oe_" + digest(identity)[:24], **identity, "text": text})
    return result


class EvidenceIndex:
    def __init__(self, state_dir: str | Path):
        self.root = Path(state_dir)
        if self.root.exists() and self.root.is_symlink():
            raise EvidenceError("unsafe_state_path")
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.root / "snapshot.json"
        self.status_path = self.root / "status.json"
        self.lock_path = self.root / "sync.lock"

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        if path.is_symlink():
            raise EvidenceError("unsafe_state_path")
        try:
            if path.stat().st_size > 60_000_000:
                raise EvidenceError("index_size_exceeded")
            result = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise EvidenceError("corrupt_index")
            return result
        except (OSError, ValueError, UnicodeError):
            raise EvidenceError("corrupt_index") from None

    @staticmethod
    def _atomic_json(path: Path, value: dict) -> None:
        # Same-directory replace leaves either the old or new complete snapshot.
        descriptor, temp_name = tempfile.mkstemp(prefix=".oe-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(canonical(value))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @contextmanager
    def _lock(self):
        try:
            handle = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise EvidenceError("sync_busy") from None
        try:
            os.close(handle)
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)

    def _snapshot(self) -> dict | None:
        snapshot = self._read_json(self.snapshot_path)
        if snapshot is None:
            return None
        try:
            payload = {key: snapshot[key] for key in ("schema_version", "namespace", "documents", "tombstones")}
            if snapshot["schema_version"] != 1 or digest(payload) != snapshot["generation"]:
                raise EvidenceError("corrupt_index")
            if not isinstance(snapshot["documents"], dict):
                raise EvidenceError("corrupt_index")
            for doc in snapshot["documents"].values():
                if hashlib.sha256(doc["text"].encode("utf-8")).hexdigest() != doc["sha256"]:
                    raise EvidenceError("corrupt_index")
        except (KeyError, TypeError, AttributeError):
            raise EvidenceError("corrupt_index") from None
        return snapshot

    def sync(self, source: Source, limits: Limits | None = None, *, allow_empty: bool = False) -> dict:
        limits = limits or Limits()
        with self._lock():
            now = datetime.now(timezone.utc).isoformat()
            self._atomic_json(self.status_path, {"state": "syncing", "attempted_at": now})
            try:
                previous = self._snapshot()
                if previous is not None and previous["namespace"] != source.namespace:
                    raise EvidenceError("source_scope_changed_use_new_index")
                before = previous["documents"] if previous else {}
                objects = source.list_objects(limits)
                check_objects(objects, source.prefix, limits)
                if before and not objects and not allow_empty:
                    raise EvidenceError("empty_snapshot_requires_confirmation")
                documents = {}
                reused = downloaded = downloaded_bytes = 0
                for obj in sorted(objects, key=lambda item: item.key):
                    old = before.get(obj.key)
                    if old and old["revision"] == obj.revision and old["size"] == obj.size:
                        documents[obj.key] = old
                        reused += 1
                        continue
                    data = source.read_object(obj, limits)
                    if len(data) != obj.size or len(data) > limits.max_object_bytes:
                        raise EvidenceError("object_changed_during_read")
                    downloaded_bytes += len(data)
                    if downloaded_bytes > limits.max_total_bytes:
                        raise EvidenceError("total_byte_budget_exceeded")
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        raise EvidenceError("invalid_utf8_object") from None
                    if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
                        raise EvidenceError("binary_object_rejected")
                    if any(len(line) > 4000 for line in text.splitlines()):
                        raise EvidenceError("line_budget_exceeded")
                    documents[obj.key] = {"revision": obj.revision, "size": len(data),
                                          "sha256": hashlib.sha256(data).hexdigest(), "text": text}
                    downloaded += 1
                removed = sorted(set(before) - set(documents))
                tombstones = dict(previous["tombstones"]) if previous else {}
                for key in removed:
                    tombstones[key] = {"sha256": before[key]["sha256"], "removed_from_generation": previous["generation"]}
                for key in documents:
                    tombstones.pop(key, None)
                if len(tombstones) > 10_000:
                    raise EvidenceError("tombstone_budget_exceeded")
                payload = {"schema_version": 1, "namespace": source.namespace, "documents": documents, "tombstones": tombstones}
                generation = digest(payload)
                snapshot = {**payload, "generation": generation}
                changed = previous is None or previous["generation"] != generation
                if changed:
                    self._atomic_json(self.snapshot_path, snapshot)
                report = {"state": "ready", "attempted_at": now, "generation": generation,
                          "objects": len(documents), "downloaded": downloaded, "reused": reused,
                          "deleted": len(removed), "downloaded_bytes": downloaded_bytes, "changed": changed}
                self._atomic_json(self.status_path, report)
                return report
            except EvidenceError as error:
                self._atomic_json(self.status_path, {"state": "failed", "attempted_at": now, "error": error.code})
                raise
            except Exception:
                self._atomic_json(self.status_path, {"state": "failed", "attempted_at": now, "error": "sync_failed"})
                raise EvidenceError("sync_failed") from None

    def query(self, query: str, *, limit: int = 3, allow_stale: bool = False) -> dict:
        if not isinstance(query, str) or not query.strip() or len(query) > 500 or not 1 <= limit <= 10:
            raise EvidenceError("invalid_query")
        if self.lock_path.exists():
            raise EvidenceError("sync_busy")
        snapshot = self._snapshot()
        if snapshot is None:
            raise EvidenceError("index_not_ready")
        status = self._read_json(self.status_path) or {}
        stale = status.get("state") != "ready" or status.get("generation") != snapshot["generation"]
        if stale and not allow_stale:
            raise EvidenceError("index_stale_after_failed_sync")
        corpus = []
        for key, doc in sorted(snapshot["documents"].items()):
            corpus.extend(chunks(key, doc, snapshot["namespace"]))
        query_terms = set(tokens(query))
        counters = [Counter(tokens(chunk["text"])) for chunk in corpus]
        avg_length = sum(sum(counter.values()) for counter in counters) / max(1, len(counters))
        frequency = Counter(term for counter in counters for term in counter)
        scored = []
        for chunk, counter in zip(corpus, counters):
            score = 0.0
            length = sum(counter.values())
            for term in query_terms:
                count = counter.get(term, 0)
                if count:
                    idf = math.log(1 + (len(corpus) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                    score += idf * (count * 2.2) / (count + 1.2 * (0.25 + 0.75 * length / max(1, avg_length)))
            if score > 0:
                scored.append({**chunk, "score": round(score, 6)})
        scored.sort(key=lambda item: (-item["score"], item["key"], item["start_line"]))
        return {"schema_version": 1, "query": query, "generation": snapshot["generation"],
                "stale": stale, "mode": "deterministic_lexical_retrieval", "model_calls": 0,
                "abstained": not scored, "matches": scored[:limit]}

    def documents_for_adapter(self) -> list[dict]:
        if self.lock_path.exists():
            raise EvidenceError("sync_busy")
        snapshot = self._snapshot()
        status = self._read_json(self.status_path) or {}
        if not snapshot or status.get("state") != "ready" or status.get("generation") != snapshot["generation"]:
            raise EvidenceError("index_not_ready")
        return [chunk for key, doc in sorted(snapshot["documents"].items()) for chunk in chunks(key, doc, snapshot["namespace"])]
