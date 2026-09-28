"""Run a *frozen* G3 held-out matrix on user-operated Colab CUDA."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from ruleshift.cuda_model import CudaModel
from ruleshift.web_schedule import balanced_schedule
from ruleshift.web_stream_runner import implementation_sha256, run_stream_checkpointed
from ruleshift.web_streams import make_split

PINNED = {
    "Qwen/Qwen3-4B-Instruct-2507": "cdbee75f17c01a7cc42f958dc650907174af0554",
    "microsoft/Phi-4-mini-instruct": "cfbefacb99257ffa30c83adab238a50856ac3083",
}
STRATEGIES = ("retrieval", "always_refresh", "conditional_all",
              "v1_selective", "source_dependent")


def validate_frozen_protocol(protocol: dict, model_id: str) -> tuple:
    """Reject an unfrozen, incomplete, or code-drifted formal run before GPU load."""
    if model_id not in PINNED:
        raise ValueError("Model is not pinned")
    if protocol.get("kind") != "RuleShift-Web-G3" or protocol.get("status") != "frozen":
        raise ValueError("A frozen G3 protocol is required")
    count = protocol.get("streams_per_scenario")
    if count not in (5, 10):
        raise ValueError("Only the predeclared 1,600/3,200-task scales are allowed")
    streams = make_split("test", protocol["stream_seed"], count)
    if protocol.get("stream_sha256") != [s.sha256() for s in streams]:
        raise ValueError("Held-out stream manifest mismatch")
    if protocol.get("strategies") != list(STRATEGIES):
        raise ValueError("Strategy definitions/order mismatch")
    if protocol.get("model_ids") != list(PINNED):
        raise ValueError("Model matrix mismatch")
    target = len(streams) * 8 * len(STRATEGIES) * len(PINNED)
    if protocol.get("target_model_tasks") != target:
        raise ValueError("Formal task count mismatch")
    if protocol.get("resource_decision") != ("3200" if count == 10 else "1600"):
        raise ValueError("Resource decision and task count disagree")
    if protocol.get("implementation_sha256") != implementation_sha256(CudaModel):
        raise ValueError("Implementation changed after protocol freeze")
    if protocol.get("formal_runner_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Formal runner changed after protocol freeze")
    model = protocol.get("models", {}).get(model_id, {})
    expected_adapter = "phi_json_fence_v1" if model_id.startswith("microsoft/") else "strict"
    if (model.get("revision") != PINNED[model_id]
            or model.get("format_adapter") != expected_adapter
            or model.get("slot") != list(PINNED).index(model_id)
            or not model.get("gpu") or not isinstance(model.get("runtime"), dict)):
        raise ValueError("Model revision, adapter, or schedule slot mismatch")
    preflight = protocol.get("preflight", {})
    if (set(preflight) != set(PINNED) or
            any(preflight[key].get("completed_model_tasks") != 160 for key in PINNED)):
        raise ValueError("Both 160-task development preflights are required")
    if (model["gpu"] != preflight[model_id].get("gpu") or
            model["runtime"] != preflight[model_id].get("runtime")):
        raise ValueError("Frozen model runtime differs from audited preflight")
    resource = protocol.get("resource", {})
    if (resource.get("available_ccu", 0) <= 0 or
            resource.get("projected_ccu", float("inf")) >
            resource["available_ccu"] * 0.8):
        raise ValueError("20% CCU reserve gate not satisfied")
    return streams, balanced_schedule(streams, STRATEGIES,
                                      protocol["schedule_seed"], model["slot"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(PINNED), required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    streams, schedule = validate_frozen_protocol(protocol, args.model)
    started = time.perf_counter()
    model = CudaModel(args.model, PINNED[args.model])
    load_seconds = time.perf_counter() - started
    frozen_model = protocol["models"][args.model]
    if (model.provenance["cuda_device"] != frozen_model["gpu"] or
            any(model.provenance.get(key) != value for key, value in
                frozen_model["runtime"].items())):
        raise RuntimeError("GPU or package versions differ from the frozen development preflight")
    state = run_stream_checkpointed(
        model, args.output, model.provenance, streams, STRATEGIES,
        format_adapter=protocol["models"][args.model]["format_adapter"],
        schedule=schedule,
        protocol_sha256=hashlib.sha256(protocol_bytes).hexdigest(),
    )
    with sqlite3.connect(args.output / "results.sqlite") as db:
        results = [json.loads(payload) for (payload,) in db.execute("SELECT payload FROM results")]
    tasks = [task for result in results for task in result["tasks"]]
    responses = [response for task in tasks for response in task["responses"]]
    print(json.dumps({
        "kind": "G3_frozen_held_out_run",
        "model": args.model, "revision": PINNED[args.model],
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "gpu": model.provenance["cuda_device"], "device_map": model.provenance["device_map"],
        "load_seconds_this_invocation": load_seconds,
        "wall_seconds_this_invocation": time.perf_counter() - started,
        "peak_gpu_memory_bytes": model.torch.cuda.max_memory_allocated(),
        "planned_model_tasks": len(streams) * len(STRATEGIES) * 8,
        "completed_model_tasks": len(tasks),
        "correct": sum(task["final_correct"] for task in tasks),
        "raw_format_errors": sum(task["raw_format_errors"] for task in tasks),
        "effective_format_errors": sum(task["effective_format_errors"] for task in tasks),
        "server_rejections": sum(task["server_rejections"] for task in tasks),
        "policy_reads": sum(result["setup_policy_reads"] for result in results)
                        + sum(task["policy_reads"] for task in tasks),
        "agent_http_requests": sum(result["setup_policy_reads"] for result in results)
                               + sum(task["agent_http_requests"] for task in tasks),
        "prompt_tokens": sum(r["prompt_tokens"] for r in responses),
        "completion_tokens": sum(r["completion_tokens"] for r in responses),
        "model_seconds": sum(r["seconds"] for r in responses),
        **state,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
