"""Run the frozen G3 no-LLM control on the same held-out streams locally."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ruleshift.deterministic_controller import DeterministicController
from ruleshift.web_schedule import balanced_schedule
from ruleshift.web_stream_runner import implementation_sha256, run_stream_checkpointed
from scripts.run_g3_colab_formal import PINNED, STRATEGIES, validate_frozen_protocol


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.protocol.read_bytes()
    protocol = json.loads(data)
    streams, _ = validate_frozen_protocol(protocol, next(iter(PINNED)))
    model = DeterministicController()
    control = protocol.get("control", {})
    if (control.get("model") != model.provenance["backend"]
            or control.get("revision") != model.provenance["revision"]
            or control.get("slot") != 2
            or control.get("format_adapter") != "strict"
            or control.get("implementation_sha256") !=
            implementation_sha256(DeterministicController)):
        raise ValueError("Frozen no-LLM control mismatch")
    schedule = balanced_schedule(streams, STRATEGIES, protocol["schedule_seed"], 2)
    result = run_stream_checkpointed(
        model, args.output, model.provenance, streams, STRATEGIES,
        schedule=schedule, protocol_sha256=hashlib.sha256(data).hexdigest(),
    )
    print(json.dumps({"kind": "G3_frozen_no_llm_control", **result}, sort_keys=True))


if __name__ == "__main__":
    main()
