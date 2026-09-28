"""Checkpointed, controlled v2 pilot using only agent-visible HTTP evidence.

This is a development pilot. Formal held-out streams and statistical analysis
remain G3 work. The model adapter is injected; no paid API or Codex call occurs
per task. The scheduler and scorer may inspect Lab state, but prompts may not.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
from pathlib import Path
from typing import Protocol

from fastapi.testclient import TestClient

from ruleshift.web_lab import INITIAL_POLICIES, Lab, create_app
from ruleshift.web_memory import ACTION_SOURCES, PolicyMemory

SCENARIOS = ("unchanged", "relevant_change", "unrelated_change", "reversion", "commit_race")
STRATEGIES = ("retrieval", "always_refresh", "conditional_all", "source_dependent")
ACTIONS = ("purchase", "refund", "ship", "address")
ORDER_IDS = {"refund": "RET-001", "ship": "SHIP-001", "address": "ADDR-001"}
DENY_RULES = {
    "purchase": {"eligible": False, "percent": 0},
    "refund": {"window_days": 14, "accept_opened": False},
    "ship": {"max_quantity": 1, "destinations": ["mainland"]},
    "address": {"max_age_hours": 18, "allow_express": False},
}
INTERIM_RULES = {
    "purchase": {"eligible": True, "percent": 5},
    "refund": {"window_days": 25, "accept_opened": False},
    "ship": {"max_quantity": 3, "destinations": ["mainland", "island"]},
    "address": {"max_age_hours": 48, "allow_express": True},
}
SYSTEM = (
    "You are a retail agent. Use only the supplied customer request, public order, "
    "and policy evidence. Check numeric and categorical limits exactly. Reply with "
    "one compact JSON object only: {\"attempt\":true,\"reason\":\"ok\"} or "
    "{\"attempt\":false,\"reason\":\"code\"}. Reason must be one short code: "
    "ok, too_old, opened, max_quantity, destination, locked, service_level, "
    "discount_ineligible, or uncertain. No prose, markdown, or extra keys."
)
REASON_CODES = {
    "ok", "too_old", "opened", "max_quantity", "destination", "locked",
    "service_level", "discount_ineligible", "uncertain",
}


class Model(Protocol):
    def generate(self, system: str, user: str, max_new_tokens: int = 96) -> dict: ...


def parse_decision(text: str) -> dict | None:
    try:
        value = json.loads(text.strip())
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict) or set(value) != {"attempt", "reason"}:
        return None
    if (type(value["attempt"]) is not bool or not isinstance(value["reason"], str)
            or value["reason"] not in REASON_CODES):
        return None
    if value["attempt"] != (value["reason"] == "ok"):
        return None
    return value


def public_task(client: TestClient, action: str) -> dict:
    if action == "purchase":
        return {"request": "Buy a notebook with the advertised discount.", "product": "notebook"}
    order_id = ORDER_IDS[action]
    response = client.get(f"/site/orders/{order_id}")
    assert response.status_code == 200
    return {
        "request": {"refund": "Refund this order if eligible.",
                    "ship": "Ship this order if eligible.",
                    "address": "Change the address to 20 New Street if eligible."}[action],
        "order": response.json()["order"],
    }


def ask(model: Model, action: str, task: dict, evidence: list[dict]) -> tuple[dict | None, dict]:
    # Explicit allowlist. No Lab snapshot, evaluator state, or future event enters the prompt.
    user = json.dumps({"action": action, "task": task, "policy_evidence": evidence}, sort_keys=True)
    response = model.generate(SYSTEM, user, max_new_tokens=96)
    return parse_decision(response["text"]), response


def submit(client: TestClient, action: str, policy_revision: str):
    if action == "purchase":
        return client.post("/site/purchases", json={"sku": "notebook", "request_discount": True,
                                                    "expected_policy_revision": policy_revision})
    return client.post(
        f"/site/orders/{ORDER_IDS[action]}/{action}",
        json={"expected_policy_revision": policy_revision, "address": "20 New Street"},
    )


def run_case(model: Model, action: str, scenario: str, strategy: str) -> dict:
    if action not in ACTIONS or scenario not in SCENARIOS or strategy not in STRATEGIES:
        raise ValueError("Unknown pilot condition")
    lab = Lab()
    client = TestClient(create_app(lab))
    memory = PolicyMemory()
    task = public_task(client, action)
    # Every strategy begins with identical public source observations.
    for scope in INITIAL_POLICIES:
        memory.acquire(client, scope, 0, conditional=False)
    scope = ACTION_SOURCES[action][0]
    if scenario in ("relevant_change", "reversion"):
        lab.publish(scope, DENY_RULES[action])
    if scenario == "unrelated_change":
        lab.publish("shipping", {"free_threshold": 80})
    if scenario == "reversion":
        lab.publish(scope, INITIAL_POLICIES[scope])
    if scenario == "commit_race":
        lab.publish(scope, INTERIM_RULES[action])

    evidence = memory.for_action(client, action, 1, strategy)
    decision, response = ask(model, action, task, evidence)
    initial_decision = decision
    model_responses = [response]
    action_log: list[dict] = []
    if scenario == "commit_race":
        # This event occurs after the model saw evidence but before submission.
        lab.publish(scope, DENY_RULES[action])
    if decision is not None and decision["attempt"]:
        result = submit(client, action, evidence[0]["revision"])
        action_log.append({"status": result.status_code, "result": result.json()})
        if result.status_code == 409 and result.json().get("error") == "policy_revision_changed":
            # One bounded recovery, available to every strategy after server rejection.
            evidence = memory.for_action(client, action, 2, "source_dependent")
            decision, response = ask(model, action, task, evidence)
            model_responses.append(response)
            if decision is not None and decision["attempt"]:
                result = submit(client, action, evidence[0]["revision"])
                action_log.append({"status": result.status_code, "result": result.json()})

    final_state = lab.state()
    committed = bool(final_state["purchases"]) if action == "purchase" else (
        final_state["orders"][ORDER_IDS[action]]["status"] not in ("pending", "delivered")
    )
    expected_allowed = scenario in ("unchanged", "unrelated_change", "reversion")
    final_correct = (
        decision is not None
        and (committed and decision["attempt"] if expected_allowed else not committed and not decision["attempt"])
        and (scenario != "commit_race" or initial_decision is not None and initial_decision["attempt"])
    )
    assert lab.replay()["verified"]
    return {
        "action": action, "scenario": scenario, "strategy": strategy,
        "model_decision": decision,
        "initial_decision": initial_decision,
        "expected_allowed": expected_allowed,
        "committed": committed,
        "final_correct": final_correct,
        "format_errors": sum(parse_decision(r["text"]) is None for r in model_responses),
        "server_rejections": sum(e["status"] == 409 for e in action_log),
        "invalid_commits": int(committed and not expected_allowed),
        "policy_reads": sum(e["kind"] == "read" for e in lab.events),
        "prompt_tokens": sum(r["prompt_tokens"] for r in model_responses),
        "completion_tokens": sum(r["completion_tokens"] for r in model_responses),
        "model_seconds": sum(r["seconds"] for r in model_responses),
        "model_responses": model_responses,
        "memory_history": memory.history,
        "action_log": action_log,
        "trace": lab.snapshot(),
    }


def run_checkpointed(model: Model, output: Path, model_info: dict, cases: list[tuple[str, str, str]]) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    import ruleshift.web_lab as lab_module
    import ruleshift.web_memory as memory_module

    source_hash = hashlib.sha256()
    for path in (Path(__file__), Path(lab_module.__file__), Path(memory_module.__file__)):
        source_hash.update(path.read_bytes())
    model_path = Path(inspect.getfile(type(model)))
    source_hash.update(model_path.read_bytes() if model_path.is_file() else repr(type(model)).encode())
    manifest = {"schema_version": 1, "model": model_info, "cases": [list(case) for case in cases],
                "kind": "G2_development_pilot", "implementation_sha256": source_hash.hexdigest()}
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("Existing checkpoint has a different model or case matrix")
    else:
        temporary = output / "manifest.json.tmp"
        temporary.write_text(json.dumps(manifest, sort_keys=True, indent=2))
        temporary.replace(manifest_path)
    with sqlite3.connect(output / "results.sqlite") as con:
        con.execute("CREATE TABLE IF NOT EXISTS results (case_key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        for action, scenario, strategy in cases:
            key = json.dumps([action, scenario, strategy], separators=(",", ":"))
            if con.execute("SELECT 1 FROM results WHERE case_key = ?", (key,)).fetchone():
                continue
            result = run_case(model, action, scenario, strategy)
            con.execute("INSERT INTO results VALUES (?, ?)", (key, json.dumps(result, sort_keys=True)))
            con.commit()  # Each task stream survives runtime interruption.
        count = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
    return {"completed": count, "planned": len(cases), "complete": count == len(cases)}
