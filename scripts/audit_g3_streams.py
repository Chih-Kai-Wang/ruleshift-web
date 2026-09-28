"""Independently audit a G3 candidate checkpoint; analyze only complete test sets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

from ruleshift.web_batch import SYSTEM
from ruleshift.web_lab import INITIAL_POLICIES, revision, verify_snapshot
from ruleshift.web_schedule import balanced_schedule
from ruleshift.web_stream_runner import parse_for_g3
from ruleshift.web_streams import FOCUS_SCOPE, SCENARIOS, make_split, make_stream

BASELINES = ("retrieval", "always_refresh", "conditional_all", "v1_selective")
ALL_STRATEGIES = (*BASELINES, "source_dependent")
BOOTSTRAP_SEED = 20260928
BOOTSTRAP_DRAWS = 10000


def _spec_from_id(stream_id: str, seed: int):
    prefix, scenario, index = stream_id.rsplit("-", 2)
    split = {"dev": "development", "tes": "test"}[prefix]
    return make_stream(split, scenario, int(index), seed)


def _eligibility(action: str, task: dict, rule: dict) -> bool:
    if action == "purchase":
        return rule["eligible"]
    order = task["order"]
    if action == "refund":
        return order["age_days"] <= rule["window_days"] and (
            not order["opened"] or rule["accept_opened"]
        )
    if action == "ship":
        return order["quantity"] <= rule["max_quantity"] and (
            order["destination"] in rule["destinations"]
        )
    return order["age_hours"] <= rule["max_age_hours"] and (
        order["service"] != "express" or rule["allow_express"]
    )


def audit_row(row: dict, seed: int = 20260928,
              require_provenance: bool = False) -> dict:
    spec = _spec_from_id(row["stream_id"], seed)
    if spec.sha256() != row["spec_sha256"] or len(row["tasks"]) != 8:
        raise ValueError(f"Stream specification mismatch: {row['stream_id']}")
    expected_policies = copy.deepcopy(INITIAL_POLICIES)
    expected_policies[FOCUS_SCOPE[spec.action]] = spec.initial_rule
    expected_orders = {task["request_id"]: task["order"] for task in spec.tasks
                       if "order" in task}
    if (row["trace"].get("initial_policies") != expected_policies
            or row["trace"].get("initial_orders", {}) != expected_orders):
        raise ValueError(f"Initial world mismatch: {row['stream_id']}")
    replay = verify_snapshot(row["trace"])
    if not replay["verified"]:
        raise ValueError(f"Origin replay failed: {row['stream_id']}")
    adapter = row.get("format_adapter", "strict")
    active = spec.initial_rule
    correct = initial_correct = rejections = raw_errors = effective_errors = 0
    reads = http_requests = prompt_tokens = completion_tokens = 0
    model_seconds = revision_conflicts = policy_blocks = stale_memory_errors = 0
    invalid_commits = stale_evidence = 0
    trace_events = row["trace"]["events"]
    if row["setup_policy_reads"] != 5 or len(trace_events) < 5:
        raise ValueError(f"Setup reads missing: {row['stream_id']}")
    if [event["request"]["scope"] for event in trace_events[:5]
            if event["kind"] == "read"] != ["discount", "shipping", "returns",
                                                   "fulfillment", "changes"]:
        raise ValueError(f"Setup source mismatch: {row['stream_id']}")
    cursor = 5
    for step, (generated, recorded) in enumerate(zip(spec.tasks, row["tasks"], strict=True)):
        for publication in spec.publications:
            if publication["before_step"] == step:
                event = trace_events[cursor]
                if (event["kind"] != "publish" or event["request"] != {
                    "scope": publication["scope"], "rule": publication["rule"]
                }):
                    raise ValueError(f"Publication mismatch: {row['stream_id']} step {step}")
                cursor += 1
                if publication["scope"] == FOCUS_SCOPE[spec.action]:
                    active = publication["rule"]
        task_begin = cursor
        events = recorded["events"]
        if trace_events[cursor:cursor + len(events)] != events:
            raise ValueError(f"Task event slice mismatch: {row['stream_id']} step {step}")
        cursor += len(events)
        expected = _eligibility(spec.action, generated, active)
        responses = recorded["responses"]
        if require_provenance and ("task_public" not in recorded or
                                   "evidence_views" not in recorded):
            raise ValueError(f"Agent evidence missing: {row['stream_id']} step {step}")
        if "evidence_views" in recorded:
            public_task = ({"request": generated["request"], "product": "notebook"}
                           if spec.action == "purchase" else {
                               "request": {"refund": "Refund this order if eligible.",
                                           "ship": "Ship this order if eligible.",
                                           "address": "Change the address to 20 New Street if eligible."
                                           }[spec.action],
                               "order": generated["order"],
                           })
            if (recorded["task_public"] != public_task or
                    len(recorded["evidence_views"]) != len(responses)):
                raise ValueError(f"Agent input mismatch: {row['stream_id']} step {step}")
            last_call_seq = task_begin
            for response, evidence in zip(responses, recorded["evidence_views"], strict=True):
                seq = response["event_seq_before_model"]
                if not task_begin <= last_call_seq <= seq <= cursor:
                    raise ValueError(f"Model call sequence mismatch: {row['stream_id']} step {step}")
                last_call_seq = seq
                expected_input = {"action": spec.action, "task": public_task,
                                  "policy_evidence": evidence}
                if (json.loads(response["agent_input"]) != expected_input or
                        set(expected_input) != set(json.loads(response["agent_input"])) or
                        response["system_prompt_sha256"] != hashlib.sha256(SYSTEM.encode()).hexdigest()):
                    raise ValueError(f"Prompt provenance mismatch: {row['stream_id']} step {step}")
                if len(evidence) != 1:
                    raise ValueError(f"Evidence count mismatch: {row['stream_id']} step {step}")
                entry = evidence[0]
                prior_reads = [event for event in trace_events[:seq]
                               if event["kind"] == "read"
                               and event["status"] == 200
                               and event["request"]["scope"] == entry["scope"]]
                if (set(entry) != {"scope", "source_url", "observed_at", "etag", "revision",
                                   "policy", "depends_on", "last_validated_at"}
                        or entry["scope"] != FOCUS_SCOPE[spec.action]
                        or entry["source_url"] != f"/site/policies/{entry['scope']}"
                        or entry["depends_on"] != [entry["source_url"]]
                        or entry["revision"] != entry["policy"].get("revision")
                        or entry["etag"] != '"' + revision(entry["policy"]) + '"'
                        or not any(event["response"] == entry["policy"]
                                   for event in prior_reads)):
                    raise ValueError(f"Future or invented evidence: {row['stream_id']} step {step}")
        initial = parse_for_g3(responses[0]["text"], adapter)
        final = parse_for_g3(responses[-1]["text"], adapter)
        commits = [event for event in recorded["events"]
                   if event["kind"] == ("purchase" if spec.action == "purchase" else "operate")
                   and event["status"] in (200, 201)]
        committed = bool(commits)
        valid = final is not None and final["attempt"] == expected and committed == expected
        if "evidence_views" in recorded:
            stale = recorded["evidence_views"][0][0]["revision"] != revision(active)
            stale_error = bool(stale and initial is not None and initial["attempt"] != expected)
            conflicts = sum(event["response"].get("error") == "policy_revision_changed"
                            for event in events if event["kind"] in ("purchase", "operate"))
            blocks = sum(event["response"].get("error") == "policy_block"
                         for event in events if event["kind"] in ("purchase", "operate"))
            if (recorded["stale_evidence_at_first_decision"] != stale or
                    recorded["stale_memory_error"] != stale_error or
                    recorded["revision_conflicts"] != conflicts or
                    recorded["policy_blocks"] != blocks or
                    recorded["invalid_commits"] != int(committed and not expected)):
                raise ValueError(f"Failure taxonomy mismatch: {row['stream_id']} step {step}")
            stale_evidence += int(stale)
            stale_memory_errors += int(stale_error)
            revision_conflicts += conflicts
            policy_blocks += blocks
            invalid_commits += int(committed and not expected)
        if (recorded["step"] != step or recorded["request_id"] != generated["request_id"]
                or recorded["expected_allowed"] != expected or recorded["committed"] != committed
                or recorded["final_correct"] != valid
                or recorded["initial_decision"] != initial or recorded["final_decision"] != final):
            raise ValueError(f"Task score mismatch: {row['stream_id']} step {step}")
        correct += int(valid)
        initial_correct += int(initial is not None and initial["attempt"] == expected)
        rejections += sum(event["status"] == 409 for event in recorded["events"]
                          if event["kind"] in ("purchase", "operate"))
        raw_errors += sum(parse_for_g3(response["text"]) is None for response in responses)
        effective_errors += sum(parse_for_g3(response["text"], adapter) is None
                                for response in responses)
        for response in responses:
            if (type(response.get("prompt_tokens")) is not int
                    or type(response.get("completion_tokens")) is not int
                    or type(response.get("seconds")) not in (int, float)
                    or response["prompt_tokens"] < 0 or response["completion_tokens"] < 0
                    or not math.isfinite(response["seconds"]) or response["seconds"] < 0):
                raise ValueError(f"Invalid model telemetry: {row['stream_id']} step {step}")
            prompt_tokens += response["prompt_tokens"]
            completion_tokens += response["completion_tokens"]
            model_seconds += response["seconds"]
        reads += sum(event["kind"] == "read" for event in recorded["events"])
        task_requests = sum(event["kind"] in ("read", "inspect_order", "purchase", "operate")
                            for event in recorded["events"])
        if recorded.get("agent_http_requests", task_requests) != task_requests:
            raise ValueError(f"HTTP request count mismatch: {row['stream_id']} step {step}")
        http_requests += task_requests
    if reads != sum(task["policy_reads"] for task in row["tasks"]):
        raise ValueError(f"Read count mismatch: {row['stream_id']}")
    if cursor != len(trace_events):
        raise ValueError(f"Unattributed origin events: {row['stream_id']}")
    return {"stream_id": spec.stream_id, "split": spec.split, "scenario": spec.scenario,
            "strategy": row["strategy"], "correct": correct, "tasks": 8,
            "initial_correct": initial_correct,
            "server_rejections": rejections, "raw_format_errors": raw_errors,
            "effective_format_errors": effective_errors,
            "stale_evidence_first_decision": stale_evidence,
            "stale_memory_errors": stale_memory_errors,
            "revision_conflicts": revision_conflicts,
            "policy_blocks": policy_blocks, "invalid_commits": invalid_commits,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "model_seconds": model_seconds,
            "policy_reads": row["setup_policy_reads"] + reads,
            "agent_http_requests": row["setup_policy_reads"] + http_requests}


def _paired_interval(rows: list[dict], baseline: str,
                     metric: str = "correct", label: str = "accuracy") -> dict:
    by_key = {(row["stream_id"], row["strategy"]): row for row in rows}
    ids_by_scenario = {scenario: sorted({row["stream_id"] for row in rows
                                         if row["scenario"] == scenario})
                       for scenario in SCENARIOS}
    differences = {stream_id: (by_key[(stream_id, "source_dependent")][metric]
                               - by_key[(stream_id, baseline)][metric]) / 8
                   for ids in ids_by_scenario.values() for stream_id in ids}
    observed = sum(differences.values()) / len(differences)
    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        selected = [rng.choice(ids) for ids in ids_by_scenario.values()
                    for _ in range(len(ids))]
        draws.append(sum(differences[stream_id] for stream_id in selected) / len(selected))
    draws.sort()
    return {"baseline": baseline, f"mean_{label}_difference": observed,
            "ci95": [draws[249], draws[9749]], "streams": len(differences),
            "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_draws": BOOTSTRAP_DRAWS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.checkpoint / "manifest.json").read_text())
    formal = manifest.get("kind") == "G3_formal_stream"
    if formal and args.protocol is None:
        parser.error("Formal checkpoint audit requires --protocol")
    if not formal and args.protocol is not None:
        parser.error("Development checkpoint must not use a formal protocol")
    protocol = json.loads(args.protocol.read_text()) if args.protocol else None
    seed = protocol["stream_seed"] if protocol else 20260928
    if protocol:
        digest = hashlib.sha256(args.protocol.read_bytes()).hexdigest()
        if (protocol.get("kind") != "RuleShift-Web-G3"
                or protocol.get("status") != "frozen"
                or protocol.get("audit_script_sha256") !=
                hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                or manifest.get("protocol_sha256") != digest):
            raise ValueError("Formal protocol provenance mismatch")
        model_id = manifest["model"].get("model", manifest["model"].get("backend"))
        control = model_id == "deterministic_public_evidence"
        model = protocol["control"] if control else protocol["models"][model_id]
        expected_hash = (model["implementation_sha256"] if control else
                         protocol["implementation_sha256"])
        if manifest.get("implementation_sha256") != expected_hash:
            raise ValueError("Formal implementation provenance mismatch")
        streams = make_split("test", seed, protocol["streams_per_scenario"])
        expected_schedule = balanced_schedule(
            streams, tuple(protocol["strategies"]), protocol["schedule_seed"], model["slot"]
        )
        if (manifest.get("streams") != [s.sha256() for s in streams]
                or protocol.get("stream_sha256") != [s.sha256() for s in streams]
                or manifest.get("schedule") != [list(item) for item in expected_schedule]
                or manifest.get("format_adapter") != model["format_adapter"]
                or manifest["model"]["revision"] != model["revision"]
                or (not control and manifest["model"].get("cuda_device") != model["gpu"])
                or (not control and any(manifest["model"].get(key) != value
                                     for key, value in model["runtime"].items()))):
            raise ValueError("Formal manifest/matrix mismatch")
    with sqlite3.connect(f"file:{args.checkpoint / 'results.sqlite'}?mode=ro", uri=True) as db:
        stored = [(json.loads(key), json.loads(payload))
                  for key, payload in db.execute("SELECT case_key, payload FROM results ORDER BY rowid")]
        has_failures_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='failures'"
        ).fetchone() is not None
        failures = ([json.loads(payload) for (payload,) in db.execute("SELECT payload FROM failures")]
                    if has_failures_table else [])
    for key, row in stored:
        if (key != [row["stream_id"], row["spec_sha256"], row["strategy"]]
                or row.get("format_adapter") != manifest["format_adapter"]):
            raise ValueError("Checkpoint key, payload, or response adapter mismatch")
    if formal and [[key[0], key[2]] for key, _ in stored] != [
        list(item) for item in manifest["schedule"][:len(stored)]
    ]:
        raise ValueError("Formal checkpoint execution order mismatch")
    raw = [row for _, row in stored]
    rows = [audit_row(row, seed, require_provenance=formal) for row in raw]
    if len({(row["stream_id"], row["strategy"]) for row in rows}) != len(rows):
        raise ValueError("Duplicate stream/strategy result")
    by_strategy = defaultdict(lambda: {"streams": 0, "tasks": 0, "correct": 0,
                                       "initial_correct": 0, "server_rejections": 0,
                                       "stale_evidence_first_decision": 0,
                                       "stale_memory_errors": 0,
                                       "revision_conflicts": 0, "policy_blocks": 0,
                                       "invalid_commits": 0,
                                       "prompt_tokens": 0, "completion_tokens": 0,
                                       "model_seconds": 0.0, "policy_reads": 0,
                                       "agent_http_requests": 0,
                                       "raw_format_errors": 0, "effective_format_errors": 0})
    for row in rows:
        aggregate = by_strategy[row["strategy"]]
        aggregate["streams"] += 1
        for metric in ("tasks", "correct", "initial_correct", "server_rejections",
                       "stale_evidence_first_decision", "stale_memory_errors",
                       "revision_conflicts", "policy_blocks", "invalid_commits",
                       "prompt_tokens", "completion_tokens", "model_seconds", "policy_reads",
                       "agent_http_requests",
                       "raw_format_errors", "effective_format_errors"):
            aggregate[metric] += row[metric]
    observed_keys = {(row["stream_id"], row["strategy"]) for row in rows}
    expected_keys = ({(stream.stream_id, strategy) for stream in streams
                      for strategy in ALL_STRATEGIES} if protocol else set())
    complete_test = bool(protocol and observed_keys == expected_keys and not failures)
    result = {"kind": "G3_independent_checkpoint_audit",
              "model": manifest["model"], "streams_audited": len(rows),
              "recorded_failures": failures,
              "by_strategy": dict(by_strategy), "formal_analysis_enabled": complete_test,
              "paired": ([_paired_interval(rows, baseline) for baseline in BASELINES]
                         if complete_test else []),
              "paired_http_requests": ([_paired_interval(
                  rows, baseline, "agent_http_requests", "http_requests_per_task"
              ) for baseline in BASELINES] if complete_test else []),
              "limit": ("Frozen held-out matrix; interpret paired estimates only "
                        "with both model checkpoints and resource record."
                        if formal else "Development/preflight records cannot be "
                                       "reported as held-out results.")}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
