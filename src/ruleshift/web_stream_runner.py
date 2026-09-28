"""Candidate sequential G3 runner; not a frozen held-out experiment."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import re
import sqlite3
import traceback
from pathlib import Path

from fastapi.testclient import TestClient

from ruleshift.web_batch import SYSTEM, Model, ask, parse_decision
from ruleshift.web_lab import INITIAL_POLICIES, Lab, create_app, revision
from ruleshift.web_memory import PolicyMemory
from ruleshift.web_streams import FOCUS_SCOPE, StreamSpec

_JSON_FENCE = re.compile(r"\s*```json\s*\n(?P<body>.*?)\n\s*```\s*",
                         re.DOTALL | re.IGNORECASE)


def parse_for_g3(text: str, adapter: str = "strict") -> dict | None:
    """Bounded development adapter; never repairs contradictory decisions."""
    if adapter not in ("strict", "phi_json_fence_v1"):
        raise ValueError("Unknown response adapter")
    parsed = parse_decision(text)
    if parsed is not None or adapter == "strict":
        return parsed
    match = _JSON_FENCE.fullmatch(text)
    return parse_decision(match.group("body").strip()) if match else None


def _ask(model: Model, action: str, task: dict, evidence: list[dict],
         adapter: str, event_seq: int):
    _, response = ask(model, action, task, evidence)
    recorded = dict(response)
    recorded["agent_input"] = json.dumps(
        {"action": action, "task": task, "policy_evidence": evidence}, sort_keys=True
    )
    recorded["system_prompt_sha256"] = hashlib.sha256(SYSTEM.encode()).hexdigest()
    recorded["event_seq_before_model"] = event_seq
    return parse_for_g3(response["text"], adapter), recorded


def _public_task(client: TestClient, action: str, task: dict) -> dict:
    if action == "purchase":
        return {"request": task["request"], "product": "notebook"}
    response = client.get(f"/site/orders/{task['request_id']}")
    if response.status_code != 200:
        raise RuntimeError("Generated order missing from public site")
    return {"request": {"refund": "Refund this order if eligible.",
                        "ship": "Ship this order if eligible.",
                        "address": "Change the address to 20 New Street if eligible."}[action],
            "order": response.json()["order"]}


def _allowed(lab: Lab, action: str, task: dict) -> bool:
    # Privileged scorer; never serialized into a model prompt.
    policy = lab.policies[FOCUS_SCOPE[action]]
    if action == "purchase":
        return policy["eligible"]
    order = lab.orders[task["request_id"]]
    if action == "refund":
        return (order["status"] == "delivered"
                and order["age_days"] <= policy["window_days"]
                and (not order["opened"] or policy["accept_opened"]))
    if action == "ship":
        return (order["status"] == "pending"
                and order["quantity"] <= policy["max_quantity"]
                and order["destination"] in policy["destinations"])
    return (order["status"] == "pending"
            and order["age_hours"] <= policy["max_age_hours"]
            and (order["service"] != "express" or policy["allow_express"]))


def _submit(client: TestClient, action: str, task: dict, revision: str):
    if action == "purchase":
        return client.post("/site/purchases", json={"sku": "notebook", "request_discount": True,
                                                     "expected_policy_revision": revision})
    return client.post(f"/site/orders/{task['request_id']}/{action}", json={
        "expected_policy_revision": revision, "address": "20 New Street",
    })


def run_stream(model: Model, spec: StreamSpec, strategy: str,
               format_adapter: str = "strict") -> dict:
    if strategy not in ("retrieval", "always_refresh", "conditional_all",
                        "source_dependent", "v1_selective"):
        raise ValueError("Unknown candidate G3 strategy")
    if len(spec.tasks) != 8:
        raise ValueError("Expected eight sequential tasks")
    if format_adapter not in ("strict", "phi_json_fence_v1"):
        raise ValueError("Unknown response adapter")
    initial_policies = copy.deepcopy(INITIAL_POLICIES)
    initial_policies[FOCUS_SCOPE[spec.action]] = copy.deepcopy(spec.initial_rule)
    initial_orders = {task["request_id"]: copy.deepcopy(task["order"])
                      for task in spec.tasks if "order" in task}
    lab = Lab(initial_policies, initial_orders)
    client = TestClient(create_app(lab))
    memory = PolicyMemory()
    for scope in initial_policies:
        memory.acquire(client, scope, 0, conditional=False)
    setup_policy_reads = sum(event["kind"] == "read" for event in lab.events)
    rows = []
    for step, generated_task in enumerate(spec.tasks):
        for publication in spec.publications:
            if publication["before_step"] == step:
                lab.publish(publication["scope"], publication["rule"])
        event_start = len(lab.events)
        history_start = len(memory.history)
        task = _public_task(client, spec.action, generated_task)
        expected_allowed = _allowed(lab, spec.action, generated_task)
        evidence = memory.for_action(client, spec.action, step + 1, strategy)
        initial_evidence = copy.deepcopy(evidence)
        stale_evidence = initial_evidence[0]["revision"] != revision(
            lab.policies[FOCUS_SCOPE[spec.action]]
        )
        initial_decision, response = _ask(model, spec.action, task, evidence,
                                          format_adapter, len(lab.events))
        final_decision = initial_decision
        responses = [response]
        evidence_views = [initial_evidence]
        attempts = []
        if initial_decision is not None and initial_decision["attempt"]:
            result = _submit(client, spec.action, generated_task, evidence[0]["revision"])
            attempts.append({"status": result.status_code, "result": result.json()})
            error = result.json().get("error") if result.status_code == 409 else None
            if error == "policy_revision_changed" or (
                strategy == "v1_selective" and error == "policy_block"
            ):
                evidence = memory.for_action(client, spec.action, step + 1.5,
                                             "source_dependent")
                final_decision, response = _ask(model, spec.action, task, evidence,
                                                format_adapter, len(lab.events))
                responses.append(response)
                evidence_views.append(copy.deepcopy(evidence))
                if final_decision is not None and final_decision["attempt"]:
                    result = _submit(client, spec.action, generated_task, evidence[0]["revision"])
                    attempts.append({"status": result.status_code, "result": result.json()})
        if spec.action == "purchase":
            committed = any(event["kind"] == "purchase" and event["status"] == 201
                            for event in lab.events[event_start:])
        else:
            committed = lab.orders[generated_task["request_id"]]["status"] not in (
                "pending", "delivered"
            )
        correct = (final_decision is not None and
                   final_decision["attempt"] == expected_allowed and
                   committed == expected_allowed)
        rows.append({
            "step": step, "request_id": generated_task["request_id"],
            "task_public": copy.deepcopy(task), "evidence_views": evidence_views,
            "expected_allowed": expected_allowed, "committed": committed,
            "initial_decision": initial_decision, "final_decision": final_decision,
            "final_correct": correct, "responses": responses, "attempts": attempts,
            "memory_history": copy.deepcopy(memory.history[history_start:]),
            "events": copy.deepcopy(lab.events[event_start:]),
            "raw_format_errors": sum(parse_decision(r["text"]) is None for r in responses),
            "effective_format_errors": sum(parse_for_g3(r["text"], format_adapter) is None
                                           for r in responses),
            "policy_reads": sum(event["kind"] == "read" for event in lab.events[event_start:]),
            "agent_http_requests": sum(event["kind"] in ("read", "inspect_order", "purchase", "operate")
                                       for event in lab.events[event_start:]),
            "server_rejections": sum(attempt["status"] == 409 for attempt in attempts),
            "revision_conflicts": sum(attempt["result"].get("error") == "policy_revision_changed"
                                      for attempt in attempts),
            "policy_blocks": sum(attempt["result"].get("error") == "policy_block"
                                 for attempt in attempts),
            "stale_evidence_at_first_decision": stale_evidence,
            "stale_memory_error": bool(stale_evidence and initial_decision is not None
                                       and initial_decision["attempt"] != expected_allowed),
            "invalid_commits": int(committed and not expected_allowed),
        })
    replay = lab.replay()
    if not replay["verified"]:
        raise RuntimeError(f"Stream replay failed: {replay}")
    return {"kind": "G3_candidate_sequential_stream", "stream_id": spec.stream_id,
            "spec_sha256": spec.sha256(), "strategy": strategy,
            "format_adapter": format_adapter,
            "setup_policy_reads": setup_policy_reads, "tasks": rows,
            "trace": lab.snapshot(), "replay": replay}


def run_stream_checkpointed(model: Model, output: Path, model_info: dict,
                            streams: tuple[StreamSpec, ...], strategies: tuple[str, ...],
                            format_adapter: str = "strict",
                            schedule: tuple[tuple[str, str], ...] | None = None,
                            protocol_sha256: str | None = None) -> dict:
    """Commit one complete eight-task stream/strategy record at a time."""
    output.mkdir(parents=True, exist_ok=True)
    expected = {(spec.stream_id, strategy) for spec in streams for strategy in strategies}
    if len(expected) != len(streams) * len(strategies):
        raise ValueError("Duplicate stream or strategy in matrix")
    if schedule is None:
        schedule = tuple((spec.stream_id, strategy) for spec in streams for strategy in strategies)
    if len(schedule) != len(expected) or set(schedule) != expected:
        raise ValueError("Schedule must include every stream/strategy exactly once")
    if protocol_sha256 is not None and (len(protocol_sha256) != 64 or
                                         any(c not in "0123456789abcdef" for c in protocol_sha256)):
        raise ValueError("Invalid protocol digest")
    manifest = {"kind": "G3_formal_stream" if protocol_sha256 else "G3_candidate_sequential_stream",
                "schema_version": 2,
                "model": model_info, "streams": [s.sha256() for s in streams],
                "strategies": list(strategies), "format_adapter": format_adapter,
                "schedule": [list(item) for item in schedule],
                "protocol_sha256": protocol_sha256,
                "implementation_sha256": implementation_sha256(type(model))}
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("Existing checkpoint has a different implementation or matrix")
    else:
        temporary = output / "manifest.json.tmp"
        temporary.write_text(json.dumps(manifest, sort_keys=True, indent=2))
        temporary.replace(manifest_path)
    planned = len(schedule)
    by_id = {spec.stream_id: spec for spec in streams}
    with sqlite3.connect(output / "results.sqlite") as con:
        con.execute("CREATE TABLE IF NOT EXISTS results (case_key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS failures (case_key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        expected_keys = {json.dumps([stream_id, by_id[stream_id].sha256(), strategy],
                                    separators=(",", ":")) for stream_id, strategy in schedule}
        stored_keys = {key for (key,) in con.execute("SELECT case_key FROM results")}
        if stored_keys - expected_keys:
            raise ValueError("Existing checkpoint contains unexpected cases")
        failed_keys = {key for (key,) in con.execute("SELECT case_key FROM failures")}
        if failed_keys:
            raise RuntimeError("Checkpoint contains recorded failures; audit before resuming")
        for stream_id, strategy in schedule:
            spec = by_id[stream_id]
            key = json.dumps([stream_id, spec.sha256(), strategy], separators=(",", ":"))
            if key in stored_keys:
                continue
            try:
                result = run_stream(model, spec, strategy, format_adapter)
            except Exception as exc:
                con.execute("INSERT INTO failures VALUES (?, ?)", (key, json.dumps({
                    "stream_id": stream_id, "spec_sha256": spec.sha256(),
                    "strategy": strategy, "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "traceback": traceback.format_exc(),
                }, sort_keys=True)))
                con.commit()
                raise
            con.execute("INSERT INTO results VALUES (?, ?)",
                        (key, json.dumps(result, sort_keys=True)))
            con.commit()
        completed = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
    return {"planned": planned, "completed": completed, "complete": completed == planned}


def implementation_sha256(model_class: type) -> str:
    """Hash the exact local modules whose behavior affects stream records."""
    from ruleshift import web_batch, web_lab, web_memory, web_schedule, web_streams

    digest = hashlib.sha256()
    for module in (web_batch, web_lab, web_memory, web_schedule, web_streams):
        digest.update(Path(module.__file__).read_bytes())
    digest.update(Path(__file__).read_bytes())
    model_path = Path(inspect.getfile(model_class))
    digest.update(model_path.read_bytes() if model_path.is_file() else repr(model_class).encode())
    return digest.hexdigest()
