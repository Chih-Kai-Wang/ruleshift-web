"""Deterministic *candidate* G3 sequential-stream specifications.

These specifications do not constitute a frozen test set or run models. The
stream executor, independent split audit, and strategy port are still needed.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass

SCENARIOS = ("unchanged", "relevant_change", "unrelated_change", "reversion")
ACTIONS = ("purchase", "refund", "ship", "address")
FOCUS_SCOPE = {"purchase": "discount", "refund": "returns",
               "ship": "fulfillment", "address": "changes"}


@dataclass(frozen=True)
class StreamSpec:
    stream_id: str
    split: str
    scenario: str
    action: str
    initial_rule: dict
    changed_rule: dict
    tasks: tuple[dict, ...]
    publications: tuple[dict, ...]

    def as_dict(self) -> dict:
        return asdict(self)

    def sha256(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def _rules(action: str, index: int) -> tuple[dict, dict]:
    if action == "purchase":
        return {"eligible": True, "percent": 5 + index % 20}, {"eligible": False, "percent": 0}
    if action == "refund":
        return {"window_days": 32 + index % 8, "accept_opened": False}, {
            "window_days": 5 + index % 5, "accept_opened": False,
        }
    if action == "ship":
        return {"max_quantity": 5 + index % 2,
                "destinations": ["mainland", "island"]}, {
            "max_quantity": 1, "destinations": ["mainland"],
        }
    return {"max_age_hours": 60 + index % 12, "allow_express": True}, {
        "max_age_hours": 6 + index % 8, "allow_express": False,
    }


def make_stream(split: str, scenario: str, index: int, seed: int) -> StreamSpec:
    if split not in ("development", "test") or scenario not in SCENARIOS or index < 0:
        raise ValueError("Invalid stream identity")
    stream_id = f"{split[:3]}-{scenario}-{index:02d}"
    digest = hashlib.sha256(f"{seed}:{stream_id}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    action = ACTIONS[index % len(ACTIONS)]
    initial, changed = _rules(action, index + (10 if split == "test" else 0))
    tasks = []
    for step in range(8):
        order_id = f"{stream_id}-ORDER-{step:02d}"
        if action == "purchase":
            task = {"step": step, "request_id": order_id,
                    "request": "Buy a notebook with the advertised discount."}
        elif action == "refund":
            task = {"step": step, "request_id": order_id,
                    "order": {"id": order_id, "kind": "returns", "sku": "notebook",
                              "quantity": 1, "status": "delivered",
                              "age_days": 15 + rng.randrange(10), "opened": False}}
        elif action == "ship":
            task = {"step": step, "request_id": order_id,
                    "order": {"id": order_id, "kind": "fulfillment", "sku": "lamp",
                              "quantity": 2 + rng.randrange(3), "status": "pending",
                              "destination": rng.choice(["mainland", "island"])}}
        else:
            task = {"step": step, "request_id": order_id,
                    "order": {"id": order_id, "kind": "changes", "sku": "lamp",
                              "quantity": 1, "status": "pending",
                              "age_hours": 24 + rng.randrange(20),
                              "service": rng.choice(["express", "standard"]),
                              "address": "10 Original Street"}}
        tasks.append(task)
    publications = []
    if scenario in ("relevant_change", "reversion"):
        publications.append({"before_step": 3, "scope": FOCUS_SCOPE[action],
                             "rule": changed})
    if scenario == "reversion":
        publications.append({"before_step": 6, "scope": FOCUS_SCOPE[action],
                             "rule": initial})
    if scenario == "unrelated_change":
        publications.append({"before_step": 3, "scope": "shipping",
                             "rule": {"free_threshold": 70 + index}})
    return StreamSpec(stream_id, split, scenario, action, initial, changed,
                      tuple(tasks), tuple(publications))


def make_split(split: str, seed: int, streams_per_scenario: int) -> tuple[StreamSpec, ...]:
    if streams_per_scenario < 1:
        raise ValueError("Need at least one stream per scenario")
    streams = tuple(make_stream(split, scenario, index, seed)
                    for scenario in SCENARIOS for index in range(streams_per_scenario))
    if len({stream.stream_id for stream in streams}) != len(streams):
        raise AssertionError("Duplicate stream ID")
    return streams


def semantic_signature(stream: StreamSpec) -> str:
    """Compare content without letting distinct IDs masquerade as new cases."""
    normalized_tasks = []
    for task in stream.tasks:
        normalized = {key: value for key, value in task.items() if key != "request_id"}
        if "order" in normalized:
            normalized["order"] = {key: value for key, value in normalized["order"].items()
                                   if key != "id"}
        normalized_tasks.append(normalized)
    return json.dumps({"scenario": stream.scenario, "action": stream.action,
                       "initial_rule": stream.initial_rule,
                       "changed_rule": stream.changed_rule,
                       "tasks": normalized_tasks,
                       "publications": stream.publications}, sort_keys=True)
