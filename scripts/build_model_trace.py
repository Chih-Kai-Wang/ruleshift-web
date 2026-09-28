"""Export preserved local MLX development cases for labelled browser replay."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ruleshift.web_lab import verify_snapshot


def main() -> None:
    root = Path(__file__).parents[1] / "research" / "www2027"
    source = root / "g2-mlx-smoke-format-v2-20260928"
    manifest = json.loads((source / "manifest.json").read_text())
    with sqlite3.connect(source / "results.sqlite") as con:
        by_key = {key: json.loads(payload) for key, payload in
                  con.execute("SELECT case_key, payload FROM results")}
    cases = []
    for key in manifest["cases"]:
        encoded = json.dumps(key, separators=(",", ":"))
        if encoded not in by_key:
            raise ValueError(f"Missing model case: {key}")
        row = by_key[encoded]
        if len(row["trace"]["events"]) == 0:
            raise ValueError(f"Missing source trace: {key}")
        check = verify_snapshot(row["trace"])
        if not check["verified"]:
            raise ValueError(f"Model trace failed replay: {key}: {check}")
        cases.append(row)
    payload = {
        "execution_kind": "recorded_local_mlx_model_development_not_cuda_or_held_out",
        "model": manifest["model"],
        "implementation_sha256": manifest["implementation_sha256"],
        "cases": cases,
    }
    target = root / "web_model_trace.js"
    target.write_text("window.RULESHIFT_MODEL_TRACE = " + json.dumps(payload, sort_keys=True) + ";\n")
    print(f"Exported {len(cases)} preserved model cases to {target}")


if __name__ == "__main__":
    main()
