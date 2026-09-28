"""Freeze G3 only after two audited development GPU preflights and a CCU gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from zipfile import ZipFile

from ruleshift.cuda_model import CudaModel
from ruleshift.deterministic_controller import DeterministicController
from ruleshift.web_stream_runner import implementation_sha256
from ruleshift.web_streams import SCENARIOS, make_split, make_stream, semantic_signature
from scripts.audit_g3_streams import audit_row
from scripts.run_g3_colab_formal import PINNED, STRATEGIES

ROOT = Path(__file__).parents[1]
PREFLIGHT_ARCHIVE = ROOT / "research/www2027/ruleshift-web-g3-preflight.zip"
FORMAL_SEED = 20261003
SCHEDULE_SEED = 20261001
ASSUMED_MIN_CCU_PER_HOUR = 1.15
SAFETY_FACTOR = 2.0
SETUP_RESERVE_HOURS = 1.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archived_preflight_implementation() -> str:
    """Reconstruct the implementation hash written by the shipped preflight."""
    names = ("src/ruleshift/web_batch.py", "src/ruleshift/web_lab.py",
             "src/ruleshift/web_memory.py", "src/ruleshift/web_streams.py",
             "src/ruleshift/web_stream_runner.py", "src/ruleshift/cuda_model.py")
    digest = hashlib.sha256()
    with ZipFile(PREFLIGHT_ARCHIVE) as archive:
        for name in names:
            digest.update(archive.read(name))
    return digest.hexdigest()


def audit_preflight(checkpoint: Path, summary_path: Path, model_id: str,
                    archived_hash: str) -> dict:
    manifest_path = checkpoint / "manifest.json"
    db_path = checkpoint / "results.sqlite"
    manifest = json.loads(manifest_path.read_text())
    summary = json.loads(summary_path.read_text())
    expected_streams = tuple(make_stream("development", scenario, i, 20260928)
                             for i, scenario in enumerate(SCENARIOS))
    expected_adapter = "phi_json_fence_v1" if model_id.startswith("microsoft/") else "strict"
    if (manifest.get("kind") != "G3_candidate_sequential_stream"
            or manifest.get("model", {}).get("model") != model_id
            or manifest["model"].get("revision") != PINNED[model_id]
            or manifest["model"].get("backend") != "cuda_transformers"
            or not manifest["model"].get("cuda_device")
            or not manifest["model"].get("device_map")
            or any(str(device) in ("cpu", "disk") for device in
                   manifest["model"].get("device_map", {}).values())
            or manifest.get("streams") != [s.sha256() for s in expected_streams]
            or manifest.get("strategies") != list(STRATEGIES)
            or manifest.get("format_adapter") != expected_adapter
            or manifest.get("implementation_sha256") != archived_hash):
        raise ValueError(f"Preflight manifest mismatch for {model_id}")
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        raw = [json.loads(payload) for (payload,) in db.execute("SELECT payload FROM results")]
    audited = [audit_row(row) for row in raw]
    expected_keys = {(stream.stream_id, strategy) for stream in expected_streams
                     for strategy in STRATEGIES}
    if (len(audited) != 20 or
            {(row["stream_id"], row["strategy"]) for row in audited} != expected_keys):
        raise ValueError(f"Incomplete or duplicate preflight for {model_id}")
    if (summary.get("model") != model_id
            or summary.get("revision") != PINNED[model_id]
            or summary.get("completed_model_tasks") != 160
            or summary.get("planned_model_tasks") != 160
            or summary.get("complete") is not True
            or summary.get("format_adapter") != expected_adapter
            or summary.get("gpu") != manifest["model"]["cuda_device"]
            or summary.get("correct") != sum(row["correct"] for row in audited)
            or summary.get("raw_format_errors") != sum(row["raw_format_errors"] for row in audited)
            or summary.get("effective_format_errors") !=
            sum(row["effective_format_errors"] for row in audited)):
        raise ValueError(f"Preflight printed summary mismatch for {model_id}")
    return {"manifest_sha256": sha256(manifest_path), "sqlite_sha256": sha256(db_path),
            "summary_sha256": sha256(summary_path), "completed_model_tasks": 160,
            "raw_format_errors": sum(row["raw_format_errors"] for row in audited),
            "effective_format_errors": sum(row["effective_format_errors"] for row in audited),
            "gpu": manifest["model"]["cuda_device"],
            "runtime": {key: manifest["model"][key] for key in
                        ("python", "torch", "transformers", "accelerate", "huggingface_hub",
                         "fastapi", "httpx", "pydantic")}}


def resource_decision(observation: dict) -> tuple[int, dict]:
    before = observation["ccu_before"]
    after = observation["ccu_after"]
    wall = [observation[f"{label}_total_wall_seconds"] for label in ("qwen", "phi")]
    loads = [observation[f"{label}_total_load_seconds"] for label in ("qwen", "phi")]
    values = [before, after, *wall, *loads]
    if (any(type(value) not in (int, float) or not math.isfinite(value)
            for value in values)
            or before < after or after <= 0 or any(w <= l or l < 0 for w, l in zip(wall, loads))):
        raise ValueError("Need nonincreasing CCU balance and cumulative wall/load times")
    measured_rate = (before - after) / (sum(wall) / 3600)
    rate = max(ASSUMED_MIN_CCU_PER_HOUR, measured_rate)
    available = after
    for streams_per_scenario in (10, 5):
        multiplier = streams_per_scenario * 4 / 4  # Four-stream preflight to 40 or 20 streams.
        projected_hours = (multiplier * (sum(wall) - sum(loads)) + sum(loads)) / 3600
        projected_hours += SETUP_RESERVE_HOURS
        projected = projected_hours * rate * SAFETY_FACTOR
        if projected <= available * 0.8:
            return streams_per_scenario, {
                "ccu_before": before, "available_ccu": available,
                "observed_ccu_debit": before - after,
                "measured_ccu_per_hour": measured_rate,
                "ccu_debit_resolution": ("below_display_resolution" if before == after
                                         else "observed_positive"),
                "rate_used_ccu_per_hour": rate,
                "safety_factor": SAFETY_FACTOR,
                "setup_reserve_hours": SETUP_RESERVE_HOURS,
                "projected_wall_hours_with_setup": projected_hours,
                "projected_ccu": projected,
                "reserve_ccu": available * 0.2,
                "observation_provenance": "user-recorded Colab balances and cumulative wall/load times",
            }
    raise ValueError("Neither predeclared experiment scale preserves the 20% CCU reserve")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("qwen", "phi"):
        parser.add_argument(f"--{label}-checkpoint", type=Path, required=True)
        parser.add_argument(f"--{label}-summary", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected_archive_sha = (PREFLIGHT_ARCHIVE.parent /
                            (PREFLIGHT_ARCHIVE.name + ".sha256")).read_text().split()[0]
    if sha256(PREFLIGHT_ARCHIVE) != expected_archive_sha:
        raise ValueError("Preflight archive checksum mismatch")
    archived_hash = archived_preflight_implementation()
    mapping = {"qwen": "Qwen/Qwen3-4B-Instruct-2507",
               "phi": "microsoft/Phi-4-mini-instruct"}
    preflight = {model_id: audit_preflight(getattr(args, f"{label}_checkpoint"),
                                           getattr(args, f"{label}_summary"),
                                           model_id, archived_hash)
                 for label, model_id in mapping.items()}
    observation = json.loads(args.observations.read_text())
    count, resource = resource_decision(observation)
    streams = make_split("test", FORMAL_SEED, count)
    development = tuple(make_stream("development", scenario, i, 20260928)
                        for i, scenario in enumerate(SCENARIOS))
    if {semantic_signature(stream) for stream in development}.intersection(
            semantic_signature(stream) for stream in streams):
        raise ValueError("Development/test semantic overlap")
    from scripts import run_g3_colab_formal as formal

    protocol = {
        "kind": "RuleShift-Web-G3", "status": "frozen", "schema_version": 1,
        "resource_decision": "3200" if count == 10 else "1600",
        "target_model_tasks": len(streams) * len(STRATEGIES) * 8 * len(PINNED),
        "streams_per_scenario": count, "stream_seed": FORMAL_SEED,
        "schedule_seed": SCHEDULE_SEED,
        "stream_sha256": [stream.sha256() for stream in streams],
        "strategies": list(STRATEGIES), "model_ids": list(PINNED),
        "models": {model_id: {"revision": revision, "slot": slot,
                              "format_adapter": "strict" if slot == 0 else "phi_json_fence_v1",
                              "gpu": preflight[model_id]["gpu"],
                              "runtime": preflight[model_id]["runtime"]}
                   for slot, (model_id, revision) in enumerate(PINNED.items())},
        "control": {"model": "deterministic_public_evidence", "revision": "v2-g2-1",
                    "slot": 2, "format_adapter": "strict",
                    "implementation_sha256": implementation_sha256(DeterministicController)},
        "preflight_archive_sha256": sha256(PREFLIGHT_ARCHIVE),
        "preflight": preflight, "resource": resource,
        "implementation_sha256": implementation_sha256(CudaModel),
        "formal_runner_sha256": sha256(Path(formal.__file__)),
        "audit_script_sha256": sha256(Path(__file__).parent / "audit_g3_streams.py"),
        "analysis": {"primary": "correct_final_decision_and_state_change",
                     "unit": "paired_eight_task_stream", "stratify": "scenario",
                     "bootstrap_draws": 10000, "bootstrap_seed": 20260928,
                     "interval": "two_sided_95_percentile",
                     "secondary_paired": "agent_http_requests_per_task"},
        "inference": {"dtype": "float16", "sampling": "greedy",
                      "max_new_tokens": 96, "cpu_disk_offload": False},
        "limit": "Synthetic controlled HTTP harness; no real-site generalization.",
    }
    if args.output.exists():
        raise FileExistsError("Freeze output already exists; do not overwrite a frozen protocol")
    args.output.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output),
                      "target_model_tasks": protocol["target_model_tasks"],
                      "resource_decision": protocol["resource_decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
