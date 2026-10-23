"""Record actual offline verification. Builds locally only with --package; installs nothing."""

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def write_report(name, report):
    destination = ROOT / "evidence" / name
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "command": "python -m unittest discover -s tests -v", "runtime": f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
              "discovered": result.testsRun, "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
              "failed": len(result.failures), "errors": len(result.errors),
              "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
              "elapsed_ms": round((time.monotonic() - started) * 1000), "successful": result.wasSuccessful(),
              "scope": "Offline tests, fake B2 client and fake local-model responses; no real provider requests"}
    write_report("tests.json", report)
    print(json.dumps(report, indent=2))
    if not result.wasSuccessful():
        # Test output contains only synthetic fixtures, never production credentials.
        print(output.getvalue(), file=sys.stderr)
        return 1
    if args.package:
        wheel_dir = ROOT / ".state" / "wheel"
        wheel_dir.mkdir(parents=True, exist_ok=True)
        build = subprocess.run([sys.executable, "-c", "from setuptools.build_meta import build_wheel; build_wheel('.state/wheel')"],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
        if build.returncode:
            raise RuntimeError("local_wheel_build_failed")
        wheels = list(wheel_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("unexpected_wheel_count")
        with tempfile.TemporaryDirectory(prefix="object-evidence-wheel-") as temp:
            target = Path(temp)
            with zipfile.ZipFile(wheels[0]) as archive:
                members = archive.namelist()
                if any(not (target / name).resolve().is_relative_to(target.resolve()) for name in members):
                    raise RuntimeError("unsafe_wheel_member")
                archive.extractall(target)
            fixture_members = [name for name in members if "/fixtures/" in name]
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            executions = []
            for command in ("demo", "evaluate"):
                run = subprocess.run([sys.executable, "-m", "object_evidence", command], cwd=target,
                                     env=environment, capture_output=True, text=True, timeout=30)
                parsed = json.loads(run.stdout) if run.returncode == 0 else {}
                executions.append({"command": command, "exit_code": run.returncode,
                                   "valid_report": parsed.get("schema_version") == 1,
                                   "model_calls": parsed.get("model_calls"), "cloud_calls": parsed.get("cloud_calls")})
            smoke = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                     "method": "Local wheel build with existing setuptools; extracted to isolated temporary directory; no package installation",
                     "fixture_files_in_wheel": len(fixture_members), "commands": executions,
                     "passed": len(fixture_members) == 7 and all(item["exit_code"] == 0 and item["valid_report"] for item in executions)}
            write_report("package-smoke.json", smoke)
            print(json.dumps(smoke, indent=2))
            if not smoke["passed"]:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
