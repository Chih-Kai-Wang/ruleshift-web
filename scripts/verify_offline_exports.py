"""Verify saved deterministic and model traces against the current lab code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ruleshift.web_lab import verify_snapshot

ROOT = Path(__file__).parents[1] / "research" / "www2027"


def read_export(name: str, assignment: str) -> tuple[dict, str]:
    source = ROOT / name
    raw = source.read_text()
    prefix = f"window.{assignment} = "
    if not raw.startswith(prefix) or not raw.endswith(";\n"):
        raise ValueError(f"Unexpected JS export wrapper: {name}")
    return json.loads(raw[len(prefix):-2]), hashlib.sha256(source.read_bytes()).hexdigest()


def main() -> None:
    system, system_digest = read_export("web_lab_trace.js", "RULESHIFT_OFFLINE_TRACE")
    model, model_digest = read_export("web_model_trace.js", "RULESHIFT_MODEL_TRACE")
    checks = {"system": verify_snapshot(system["snapshot"])}
    for name, branch in system["branches"].items():
        checks[f"branch:{name}"] = verify_snapshot(branch["snapshot"])
    for index, row in enumerate(model["cases"]):
        checks[f"model:{index}"] = verify_snapshot(row["trace"])
    failed = {name: value for name, value in checks.items() if not value["verified"]}
    if failed:
        raise ValueError(f"Saved exports did not replay: {failed}")
    output = {
        "kind": "offline_export_replay_against_current_lab",
        "system_js_sha256": system_digest,
        "model_js_sha256": model_digest,
        "system_events": checks["system"]["events"],
        "deterministic_branches": len(system["branches"]),
        "saved_model_runs": len(model["cases"]),
        "verified_traces": len(checks),
        "model_execution_kind": model["execution_kind"],
        "source_implementation_sha256": model["implementation_sha256"],
    }
    target = ROOT / "G2_REPLAY_AUDIT.json"
    target.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
