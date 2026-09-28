"""Resumable, manifest-bound experiments. Completed results are never silently replaced."""

from __future__ import annotations

import hashlib
import json
import platform
import time
from pathlib import Path

from ruleshift.agents import MODEL_ID, MODEL_REVISION, POLICIES, LocalModel, Memory, run_task
from ruleshift.store import RunStore, atomic_json
from ruleshift.world import SCHEDULES, SCOPES, RuleShiftEnv, digest, replay


def implementation_hash() -> str:
    root = Path(__file__).parent
    files = ["world.py", "scoring.py", "agents.py", "experiment.py", "store.py"]
    return digest({p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files})


def warmup(schedule, split, seed) -> list:
    env = RuleShiftEnv(schedule, split)
    env.reset(seed=seed)
    env.start_task()
    observations = []
    for scope in SCOPES:
        result = json.loads(env.step({"tool": "read_policy", "args": {"scope": scope}})[0])["result"]
        observations.append(result["policy"])
    return observations


def run_experiment(root: Path, smoke=False, split=None, policies=None, model=None):
    root = Path(root)
    config = {
        "schema_version": 1,
        "model": MODEL_ID,
        "revision": MODEL_REVISION,
        "split": split or ("dev" if smoke else "test"),
        "schedules": ["stable", "recurring"] if smoke else list(SCHEDULES),
        "seeds": [17] if smoke else [101, 202, 303, 404, 505],
        "policies": policies or (["retrieval", "selective"] if smoke else list(POLICIES)),
        "tasks": 4 if smoke else 8,
        "implementation_hash": implementation_hash(),
        "tool_budget": 12,
        "memory_tokens": 1024,
        "generation_max_tokens": 180,
    }
    manifest_path = root / "manifest.json"
    protocol = Path(__file__).parents[2] / "docs" / "PROTOCOL.md"
    config["protocol_hash"] = hashlib.sha256(protocol.read_bytes()).hexdigest() if protocol.exists() else None
    lock = Path(__file__).parents[2] / "uv.lock"
    config["dependency_lock_hash"] = hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["config"] != config:
            raise RuntimeError("Run configuration or implementation changed; choose a new output directory.")
    else:
        manifest = {
            "config": config,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "host": {
                "system": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
            "planned_tasks": len(config["schedules"])
            * len(config["seeds"])
            * len(config["policies"])
            * config["tasks"],
        }
        atomic_json(manifest_path, manifest)
        source = root / "source"
        source.mkdir(parents=True, exist_ok=True)
        for name in ("world.py", "scoring.py", "agents.py", "experiment.py", "store.py", "report.py"):
            file = Path(__file__).parent / name
            if file.exists():
                (source / name).write_bytes(file.read_bytes())
        if protocol.exists():
            (source / "PROTOCOL.md").write_bytes(protocol.read_bytes())
        if lock.exists():
            (source / "uv.lock").write_bytes(lock.read_bytes())
    model = model or LocalModel()
    store = RunStore(root)
    try:
        for schedule in config["schedules"]:
            for seed in config["seeds"]:
                shared = warmup(schedule, config["split"], seed)
                for policy in config["policies"]:
                    stream = f"{schedule}-{seed}-{policy}"
                    env = RuleShiftEnv(schedule, config["split"])
                    env.reset(seed=seed)
                    memory = Memory(policy)
                    for rule in shared:
                        memory.observe(rule["scope"], rule, -1, f"warmup:{rule['scope']}")
                    previous = store.latest(stream)
                    start_index = 0
                    if previous:
                        env.restore(previous["snapshot"])
                        memory.entries = previous["memory_after"]
                        start_index = previous["task_index"] + 1
                    for index in range(start_index, config["tasks"]):
                        env.start_task()
                        task_result = run_task(env, model, memory)
                        payload = {
                            "stream": stream,
                            "schedule": schedule,
                            "seed": seed,
                            "policy": policy,
                            "task_index": index,
                            "split": config["split"],
                            "backend": "mlx",
                            **task_result,
                            "snapshot": env.snapshot(),
                        }
                        replay(payload["snapshot"])
                        store.save(stream, index, payload)
                        count = store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                        print(
                            json.dumps(
                                {
                                    "completed": count,
                                    "planned": manifest["planned_tasks"],
                                    "stream": stream,
                                    "task": index,
                                    "success": payload["score"]["success"],
                                    "seconds": round(payload["cost"]["wall_seconds"], 2),
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
        from ruleshift.report import report

        report(root)
    finally:
        store.close()


def verify_reference() -> dict:
    from ruleshift.scoring import evaluate, reference_actions

    count = 0
    for split in ("dev", "validation", "test"):
        for schedule in SCHEDULES:
            for seed in (101, 202, 303, 404, 505):
                env = RuleShiftEnv(schedule, split)
                env.reset(seed=seed)
                for _ in range(8):
                    env.start_task()
                    for action in reference_actions(env.task_start):
                        env.step(action)
                    if not evaluate(env.task_start, env.state)["success"]:
                        raise AssertionError((split, schedule, seed))
                    count += 1
                replay(env.snapshot())
    return {
        "backend": "privileged_reference_not_llm",
        "tasks": count,
        "successes": count,
        "replay_verified_streams": count // 8,
    }
