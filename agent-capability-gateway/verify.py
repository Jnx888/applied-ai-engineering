"""Run tests and export compact evidence without raw failure traces or machine paths."""

import argparse
import hashlib
import json
import platform
import sqlite3
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from demo import run_demo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("evidence"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(root), pattern="test_gateway.py")
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    duration = round(time.perf_counter() - started, 4)
    report = {
        "schema_version": 1,
        "project": "Agent Capability Gateway",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "sqlite_version": sqlite3.sqlite_version,
        "tests_run": result.testsRun,
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped) - len(result.expectedFailures) - len(result.unexpectedSuccesses),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "successful": result.wasSuccessful(),
        "duration_seconds": duration,
        "failed_test_ids": [test.id() for test, _ in result.failures + result.errors],
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("gateway.py", "fixtures.py", "demo.py", "test_gateway.py", "verify.py")
        },
        "scope": "Local standard-library contract tests; fictional data; no model or network integration",
        "unrun": ["Real identity provider", "Real outbound transport", "Production load", "Independent security certification"],
    }
    demo = run_demo()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in (("tests.json", report), ("demo.json", demo)):
        (args.output_dir / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tests_run": report["tests_run"], "passed": report["passed"],
                      "scenarios_passed": demo["passed"], "scenarios_total": demo["total"],
                      "local_outbox_effects": demo["local_outbox_effects"]}))
    return 0 if result.wasSuccessful() and demo["passed"] == demo["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
