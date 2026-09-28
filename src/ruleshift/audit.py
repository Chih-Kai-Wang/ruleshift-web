"""Read-only evidence checks, independent of the experiment runner."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import sqlite3
from pathlib import Path

from ruleshift.agents import SYSTEM, Memory, build_user, parse_action
from ruleshift.scoring import evaluate
from ruleshift.world import TOOLS, Action, digest, replay


class ByteTokenUpperBound:
    """The pinned byte-level tokenizer cannot exceed one token per UTF-8 byte here."""

    def tokens(self, text):
        return len(text.encode("utf-8"))


def audit_observations(records, config):
    from ruleshift.experiment import warmup

    memories, indices = {}, {}
    prompts = 0
    for r in sorted(records, key=lambda row: (row["stream"], row["task_index"])):
        stream, index, scope = r["stream"], r["task_index"], r["score"]["scope"]
        if index != indices.get(stream, -1) + 1:
            raise ValueError("Cannot reconcile a noncontiguous memory stream")
        if stream not in memories:
            memory = Memory(r["policy"])
            for rule in warmup(r["schedule"], config["split"], r["seed"]):
                memory.observe(rule["scope"], rule, -1, f"warmup:{rule['scope']}")
            memories[stream] = memory
        memory = memories[stream]

        def visible(memory=memory, scope=scope, index=index):
            entry = memory.entries.get(scope)
            if entry and ByteTokenUpperBound().tokens(json.dumps([entry])) > config["memory_tokens"]:
                raise ValueError("Memory requires tokenizer verification beyond the v1 byte bound")
            return memory.visible(scope, index, ByteTokenUpperBound())

        if r["memory_at_start"] != visible():
            raise ValueError("Initial memory differs from replayed observations")
        events = [e for e in r["snapshot"]["events"] if e.get("index") == index]
        obs = next(e["observation"] for e in events if e["kind"] == "start_task")
        tools = [e for e in events if e["kind"] == "tool"]
        response_index = 0
        for i, h in enumerate(r["history"]):
            if h["origin"] == "model":
                user = build_user(obs, visible(), r["history"][:i], TOOLS)
                expected = f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
                # Bare payload is used only by deterministic execution fixtures.
                if r["responses"][response_index]["prompt"] not in (user, expected):
                    raise ValueError("Recorded prompt differs from reconstructed model input")
                response_index += 1
                prompts += 1
            obs = tools[i]["observation"]
            if "policy" in h["result"]:
                rule = h["result"]["policy"]
                memory.observe(rule["scope"], rule, index, f"task:{index}:tool:{i + 1}")
            if (
                memory.policy == "selective"
                and h["origin"] == "model"
                and not obs["done"]
                and h["result"].get("error") == "policy_block"
            ):
                memory.entries.pop(scope, None)
        if memory.entries != r["memory_after"]:
            raise ValueError("Final memory differs from replayed observations")
        indices[stream] = index
    return prompts


def audit(root: Path, require_complete: bool = True, exported: bool = False) -> dict:
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    config = manifest["config"]
    source = root / "source"
    names = ("world.py", "scoring.py", "agents.py", "experiment.py", "store.py")
    archived_hash = digest({name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names})
    if archived_hash != config["implementation_hash"]:
        raise ValueError("Archived execution source does not match manifest")
    for name, field in (("PROTOCOL.md", "protocol_hash"), ("uv.lock", "dependency_lock_hash")):
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != config[field]:
            raise ValueError(f"Archived {name} does not match manifest")
    # Replaying with a different implementation would not audit the frozen semantics.
    live = Path(__file__).parent
    if any((live / name).read_bytes() != (source / name).read_bytes() for name in names):
        raise ValueError("Use the archived execution version to audit this run")
    if exported or not (root / "index.sqlite").exists():
        with gzip.open(root / "trajectories.jsonl.gz", "rt", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
    else:
        database = sqlite3.connect(f"file:{root / 'index.sqlite'}?mode=ro", uri=True)
        try:
            records = [
                json.loads(row[0])
                for row in database.execute("SELECT payload FROM tasks ORDER BY stream,task_index")
            ]
        finally:
            database.close()
    expected = set(
        itertools.product(config["schedules"], config["seeds"], config["policies"], range(config["tasks"]))
    )
    actual = [(r["schedule"], r["seed"], r["policy"], r["task_index"]) for r in records]
    if len(set(actual)) != len(actual) or set(actual) - expected:
        raise ValueError("Duplicate or unexpected matrix cells")
    if manifest["planned_tasks"] != len(expected):
        raise ValueError("Manifest planned count does not match matrix")
    missing = expected - set(actual)
    if require_complete and missing:
        raise ValueError(f"Incomplete matrix: {len(missing)} missing tasks")
    event_count = 0
    for r in records:
        snap = r["snapshot"]
        replay(snap)
        event_count += len(snap["events"])
        if evaluate(snap["task_start"], snap["state"]) != r["score"]:
            raise ValueError(f"Score mismatch in {r['stream']}:{r['task_index']}")
        if (
            snap["state"]["schedule"],
            snap["state"]["seed"],
            snap["state"]["split"],
            snap["state"]["task_index"],
        ) != (r["schedule"], r["seed"], config["split"], r["task_index"]):
            raise ValueError("Record identity does not match world")
        history, responses, cost = r["history"], r["responses"], r["cost"]
        current_events = [e for e in snap["events"] if e["kind"] == "tool" and e["index"] == r["task_index"]]
        if len(history) != len(current_events) or len(history) != cost["tool_calls"]:
            raise ValueError("Tool cost/history mismatch")
        for h, e in zip(history, current_events, strict=True):
            # Valid actions are canonicalized with optional args={} by the world.
            try:
                canonical = (
                    Action.model_validate_json(h["action"]).model_dump()
                    if isinstance(h["action"], str)
                    else Action.model_validate(h["action"]).model_dump()
                )
            except (ValueError, TypeError):
                canonical = h["action"]
            if canonical != e["action"]:
                raise ValueError("History action differs from replayed action")
            if h["result"] != e["observation"]["result"]:
                raise ValueError("Recorded tool result differs from replayed observation")
        if len(responses) != sum(h["origin"] == "model" for h in history):
            raise ValueError("Response/action count mismatch")
        model_actions = [h["action"] for h in history if h["origin"] == "model"]
        if model_actions != [parse_action(response["text"]) for response in responses]:
            raise ValueError("Model text does not match recorded actions")
        for key in ("prompt_tokens", "completion_tokens"):
            if cost[key] != sum(response[key] for response in responses):
                raise ValueError(f"Incorrect {key} total")
        if cost["policy_reads"] != sum(
            isinstance(h["action"], dict) and h["action"].get("tool") == "read_policy" for h in history
        ):
            raise ValueError("Incorrect policy read count")
        if cost["illegal_attempts"] != sum("error" in h["result"] for h in history):
            raise ValueError("Incorrect illegal-attempt count")
        if cost["tool_calls"] > config["tool_budget"] or len(responses) > 16:
            raise ValueError("Budget exceeded")
        model_seconds = sum(response["seconds"] for response in responses)
        if not math.isclose(cost["model_seconds"], model_seconds, rel_tol=0, abs_tol=1e-8):
            raise ValueError("Incorrect model time total")
        if cost["wall_seconds"] + 1e-8 < model_seconds:
            raise ValueError("Task wall time is shorter than recorded model time")
        if cost["peak_memory_bytes"] != max(
            (response.get("peak_memory_bytes", 0) for response in responses), default=0
        ):
            raise ValueError("Incorrect peak memory total")
    prompt_count = audit_observations(records, config)
    summary_path = root / "summary.json"
    if exported and summary_path.exists():
        from ruleshift.report import summarize

        if (source / "report.py").read_bytes() != (live / "report.py").read_bytes():
            raise ValueError("Use the archived report implementation to audit exported summary")
        if json.loads(summary_path.read_text()) != summarize(records, len(expected)):
            raise ValueError("Published summary differs from audited trajectories")
    return {
        "verified": True,
        "complete": not missing,
        "records": len(records),
        "planned": len(expected),
        "missing": len(missing),
        "replayed_events_including_shared_prefixes": event_count,
        "source_and_protocol_verified": True,
        "scores_and_costs_recomputed": True,
        "prompts_reconstructed": prompt_count,
        "memory_states_reconciled": True,
        "scope": "World, score, prompt, memory and recorded accounting checks; no neural rerun or independent retokenization.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument(
        "--exported", action="store_true", help="Audit released trajectories instead of SQLite"
    )
    args = parser.parse_args()
    print(json.dumps(audit(args.path, not args.allow_partial, args.exported), indent=2))


if __name__ == "__main__":
    main()
