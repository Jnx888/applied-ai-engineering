import argparse
import json
import sys
from pathlib import Path

from .demo import demo, evaluate
from .engine import EvidenceIndex
from .errors import EvidenceError
from .sources import B2Config, B2Source, LocalSource


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only object retrieval with provenance; no default model calls.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--output", type=Path, help="Public-safe fixture report path; does not export private corpus data.")
    local = commands.add_parser("sync-local")
    local.add_argument("--source", type=Path, required=True)
    local.add_argument("--state", type=Path, required=True)
    local.add_argument("--namespace", required=True, help="Stable corpus identity; change it when changing source directories.")
    local.add_argument("--prefix", default="")
    local.add_argument("--allow-empty", action="store_true")
    cloud = commands.add_parser("sync-b2")
    cloud.add_argument("--config", type=Path, required=True)
    cloud.add_argument("--state", type=Path, required=True)
    cloud.add_argument("--allow-network", action="store_true")
    cloud.add_argument("--allow-empty", action="store_true")
    query = commands.add_parser("query")
    query.add_argument("text")
    query.add_argument("--state", type=Path, required=True)
    query.add_argument("--allow-stale", action="store_true")
    extract_command = commands.add_parser("extract", help="Explicitly ask an existing local Ollama model to select a verified exact quotation.")
    extract_command.add_argument("text")
    extract_command.add_argument("--state", type=Path, required=True)
    extract_command.add_argument("--local-model", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in ("demo", "evaluate"):
            report = demo() if args.command == "demo" else evaluate()
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        elif args.command == "sync-local":
            report = EvidenceIndex(args.state).sync(LocalSource(args.source, args.prefix, args.namespace), allow_empty=args.allow_empty)
        elif args.command == "sync-b2":
            if not args.allow_network:
                raise EvidenceError("explicit_network_permission_required")
            if args.config.stat().st_size > 10_000:
                raise EvidenceError("invalid_config")
            config = json.loads(args.config.read_text(encoding="utf-8"))
            if not isinstance(config, dict) or set(config) != {"endpoint", "region", "bucket", "prefix"}:
                raise EvidenceError("invalid_config")
            source = B2Source(B2Config(**config))
            report = EvidenceIndex(args.state).sync(source, allow_empty=args.allow_empty)
        elif args.command == "extract":
            from .ollama_extractor import extract
            report = extract(EvidenceIndex(args.state).query(args.text), model=args.local_model)
        else:
            report = EvidenceIndex(args.state).query(args.text, allow_stale=args.allow_stale)
        print(json.dumps(report, indent=2))
        return 1 if args.command == "evaluate" and not report["passed"] else 0
    except EvidenceError as error:
        print(json.dumps({"error": error.code}), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError):
        print(json.dumps({"error": "invalid_input_or_unavailable_file"}), file=sys.stderr)
        return 2
