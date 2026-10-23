"""Evidence generated from actual local runs against bundled fictional documents."""

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .engine import EvidenceIndex, digest
from .errors import EvidenceError
from .sources import LocalSource

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


def fixture_source() -> LocalSource:
    return LocalSource(FIXTURE_ROOT / "docs", namespace="fixture:object-evidence")


def demo() -> dict:
    with tempfile.TemporaryDirectory(prefix="object-evidence-demo-") as temp:
        index = EvidenceIndex(Path(temp) / "index")
        first = index.sync(fixture_source())
        second = index.sync(fixture_source())
        questions = ["How do we verify a restore digest?", "What does a tombstone record after deletion?",
                     "Which capabilities does the ingestion application key need?"]
        reliability_run = evaluate()
        return {"schema_version": 1, "project": "Object Evidence", "generated_at": datetime.now(timezone.utc).isoformat(),
                "kind": "independent_working_sample", "data_classification": "fictional_public_safe_fixtures",
                "mode": "deterministic_lexical_retrieval", "model_calls": 0, "cloud_calls": 0,
                "initial_sync": first, "unchanged_sync": second,
                "questions": [index.query(question) for question in questions],
                "scenarios": reliability_run["scenarios"],
                "limits": ["No live B2 account verification", "No model generation or embedding claims",
                           "Single-operator local index; not a multi-tenant service", "Synthetic fixture results are not production outcomes"]}


def evaluate() -> dict:
    dataset = json.loads((FIXTURE_ROOT / "evaluation.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="object-evidence-eval-") as temp:
        workspace = Path(temp)
        docs = workspace / "docs"
        shutil.copytree(FIXTURE_ROOT / "docs", docs)
        source = LocalSource(docs, namespace="fixture:object-evidence")
        index = EvidenceIndex(workspace / "index")
        initial = index.sync(source)
        results = []
        for case in dataset["cases"]:
            response = index.query(case["query"], limit=3)
            keys = [item["key"] for item in response["matches"]]
            expected = case["expected_key"]
            hit = response["abstained"] if expected is None else expected in keys
            rank = keys.index(expected) + 1 if expected in keys else None
            results.append({"id": case["id"], "expected_key": expected, "retrieved_keys": keys,
                            "passed": hit, "rank": rank, "abstained": response["abstained"]})
        second = index.sync(source)
        before_failure = index.snapshot_path.read_bytes()
        (docs / "runbooks" / "corrupt.md").write_bytes(b"\xff\xfe\x00")
        failure_code = None
        try:
            index.sync(source)
        except EvidenceError as error:
            failure_code = error.code
        failed_query_code = None
        try:
            index.query("restore digest")
        except EvidenceError as error:
            failed_query_code = error.code
        stale_response = index.query("restore digest", allow_stale=True)
        atomic_preserved = before_failure == index.snapshot_path.read_bytes()
        (docs / "runbooks" / "corrupt.md").unlink()
        (docs / "runbooks" / "retention.md").unlink()
        deletion = index.sync(source)
        deleted_result = index.query("tombstone diagnostic exports retention")
        deleted_absent = all(item["key"] != "runbooks/retention.md" for item in deleted_result["matches"])
        snapshot = json.loads(index.snapshot_path.read_text(encoding="utf-8"))
        reliability = {
            "unchanged_sync_zero_downloads": second["downloaded"] == 0 and not second["changed"],
            "atomic_snapshot_preserved_on_corruption": atomic_preserved,
            "corrupt_input_rejected": failure_code == "invalid_utf8_object",
            "failed_sync_blocks_default_query": failed_query_code == "index_stale_after_failed_sync",
            "explicit_stale_read_labeled": stale_response["stale"] is True,
            "deleted_document_not_retrievable": deleted_absent and deletion["deleted"] == 1,
            "tombstone_records_deletion_without_text": "runbooks/retention.md" in snapshot["tombstones"] and
                "text" not in snapshot["tombstones"]["runbooks/retention.md"],
        }
        answerable = [row for row in results if row["expected_key"] is not None]
        report = {"schema_version": 1, "project": "Object Evidence", "generated_at": datetime.now(timezone.utc).isoformat(),
                  "dataset_id": dataset["dataset_id"], "dataset_sha256": digest(dataset),
                  "scope": dataset["provenance"], "model_calls": 0, "cloud_calls": 0,
                  "initial_generation": initial["generation"], "retrieval_cases": results,
                  "retrieval_passed": sum(row["passed"] for row in results), "retrieval_total": len(results),
                  "hit_at_3": sum(row["passed"] for row in answerable) / len(answerable),
                  "mrr_at_3": round(sum(1 / row["rank"] if row["rank"] else 0 for row in answerable) / len(answerable), 6),
                  "reliability_checks": reliability, "reliability_passed": sum(reliability.values()),
                  "reliability_total": len(reliability),
                  "scenarios": [
                      {"id": "initial", "label": "Build a cited index", "outcome": "ready",
                       "trace": ["List the complete fixture scope", "Validate byte and object budgets", "Hash and index UTF-8 documents", "Atomically publish the snapshot"],
                       "metrics": {"objects": initial["objects"], "downloaded": initial["downloaded"], "downloaded_bytes": initial["downloaded_bytes"]},
                       "generation": initial["generation"]},
                      {"id": "unchanged", "label": "Reuse unchanged objects", "outcome": "ready",
                       "trace": ["Compare source revisions with the current manifest", "Reuse validated content", "Retain identical snapshot generation"],
                       "metrics": {"reused": second["reused"], "downloaded": second["downloaded"], "downloaded_bytes": second["downloaded_bytes"]},
                       "generation": second["generation"]},
                      {"id": "corrupt", "label": "Preserve evidence on failed sync", "outcome": "rejected_safely",
                       "trace": ["Encounter invalid UTF-8 in a newly added fixture", "Reject the entire candidate snapshot", "Mark the attempt failed", "Reject ordinary queries; allow explicit labeled stale inspection"],
                       "error": failure_code, "query_error": failed_query_code,
                       "metrics": {"snapshot_preserved": atomic_preserved, "stale_read_labeled": stale_response["stale"]},
                       "generation": stale_response["generation"]},
                      {"id": "deleted", "label": "Remove deleted source evidence", "outcome": "ready",
                       "trace": ["Remove the retention fixture from the source", "Complete a successful authoritative listing", "Remove deleted text from the active index", "Keep a key/hash tombstone for provenance"],
                       "metrics": {"deleted": deletion["deleted"], "objects": deletion["objects"], "deleted_text_retrievable": not deleted_absent},
                       "generation": deletion["generation"]}
                  ],
                  "limitations": ["Handwritten in-sample retrieval set, not a generalization benchmark",
                                  "No model faithfulness, live cloud, multi-tenant authorization or production performance evaluation"]}
        report["passed"] = all(row["passed"] for row in results) and all(reliability.values())
        return report
