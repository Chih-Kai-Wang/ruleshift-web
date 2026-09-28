"""Run eight bounded v2 development cases with the cached local Qwen MLX model."""

from __future__ import annotations

import json
from pathlib import Path

from ruleshift.mlx_dev_model import MlxDevModel
from ruleshift.web_batch import run_checkpointed

CASES = [
    ("purchase", "unchanged", "retrieval"),
    ("purchase", "relevant_change", "source_dependent"),
    ("refund", "relevant_change", "retrieval"),
    ("refund", "commit_race", "source_dependent"),
    ("ship", "reversion", "conditional_all"),
    ("ship", "unrelated_change", "source_dependent"),
    ("address", "unchanged", "always_refresh"),
    ("address", "commit_race", "conditional_all"),
]


def main() -> None:
    model = MlxDevModel()
    output = Path(__file__).parents[1] / "research" / "www2027" / "g2-mlx-smoke-format-v2-20260928"
    result = run_checkpointed(model, output, model.provenance, CASES)
    print(json.dumps({"execution_kind": "local_mlx_dev_model", **result}, sort_keys=True))


if __name__ == "__main__":
    main()
