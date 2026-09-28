import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="RuleShift — agent memory in changing worlds")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify", help="Verify environment with an independent privileged reference")
    bench = sub.add_parser("benchmark", help="Run or resume real local-model experiments")
    bench.add_argument("--output", type=Path, default=Path("artifacts/runs/test-v1"))
    bench.add_argument("--smoke", action="store_true")
    bench.add_argument("--split", choices=["dev", "validation", "test"])
    report = sub.add_parser("report")
    report.add_argument("path", type=Path)
    audit = sub.add_parser("audit", help="Verify world trajectories, source and recorded accounting")
    audit.add_argument("path", type=Path)
    audit.add_argument("--exported", action="store_true")
    audit.add_argument("--allow-partial", action="store_true")
    replay = sub.add_parser("replay")
    replay.add_argument("path", type=Path)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "verify":
        from ruleshift.experiment import verify_reference

        print(json.dumps(verify_reference(), indent=2))
    elif args.command == "benchmark":
        from ruleshift.experiment import run_experiment

        run_experiment(args.output, smoke=args.smoke, split=args.split)
    elif args.command == "report":
        from ruleshift.report import report as make_report

        print(json.dumps(make_report(args.path), indent=2))
    elif args.command == "audit":
        from ruleshift.audit import audit as check_evidence

        print(json.dumps(check_evidence(args.path, not args.allow_partial, args.exported), indent=2))
    elif args.command == "replay":
        from ruleshift.world import replay as verify_replay

        payload = json.loads(args.path.read_text())
        print(json.dumps(verify_replay(payload.get("snapshot", payload)), indent=2))
    else:
        import uvicorn

        uvicorn.run("ruleshift.api:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
