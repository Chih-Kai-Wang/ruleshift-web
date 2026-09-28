"""Deterministic retail world. Research snapshots are never agent observations."""

from __future__ import annotations

import copy
import hashlib
import json
import random
from typing import Any, ClassVar, Literal

import gymnasium as gym
from gymnasium import spaces
from pydantic import BaseModel, ConfigDict, Field, ValidationError

SCOPES = ("returns", "fulfillment", "changes")
SCHEDULES = ("stable", "single", "multi", "recurring")
FAMILIES = ("returns", "fulfillment", "changes", "returns", "fulfillment", "changes", "returns", "returns")
TEMPLATES = {
    scope: {
        "dev": [f"{scope}_basic", f"{scope}_edge"],
        "validation": [f"{scope}_mixed"],
        "test": [f"{scope}_composed"],
    }
    for scope in SCOPES
}


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tool: Literal[
        "read_policy",
        "inspect_order",
        "inspect_stock",
        "fulfill_order",
        "change_order",
        "refund_order",
        "finish",
    ]
    args: dict[str, Any] = Field(default_factory=dict)


TOOLS = [
    {
        "tool": "read_policy",
        "args": {"scope": "returns|fulfillment|changes"},
        "description": "Read the authoritative current business rules for this scope.",
    },
    {
        "tool": "inspect_order",
        "args": {"order_id": "string"},
        "description": "Read an order, including age, quantity, destination and status.",
    },
    {"tool": "inspect_stock", "args": {"sku": "string"}, "description": "Read available stock."},
    {
        "tool": "fulfill_order",
        "args": {"order_id": "string"},
        "description": "Ship this pending order if current rules and stock allow it.",
    },
    {
        "tool": "change_order",
        "args": {"order_id": "string", "address": "string"},
        "description": "Change a pending order's address if current rules allow it.",
    },
    {
        "tool": "refund_order",
        "args": {"order_id": "string"},
        "description": "Refund a delivered order and return its units to stock if current rules allow it.",
    },
    {
        "tool": "finish",
        "args": {"decision": "complete|deny", "reason": "string"},
        "description": "Close task AFTER doing required work, or deny for a real restriction. Reasons: "
        "ok, too_old, opened, max_quantity, destination, out_of_stock, locked, service_level.",
    },
]


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def rules_for(split: str, scope: str, phase: str) -> dict:
    # Test values/combinations are disjoint from development and validation.
    a = phase == "A"
    values = {
        "dev": (30, 14, 6, 3, 72, 18),
        "validation": (28, 10, 5, 2, 60, 15),
        "test": (21, 7, 4, 2, 48, 12),
    }[split]
    if scope == "returns":
        body = {"window_days": values[0 if a else 1], "accept_opened": a}
    elif scope == "fulfillment":
        body = {
            "max_quantity": values[2 if a else 3],
            "destinations": ["mainland", "island"] if a else ["mainland"],
        }
    else:
        body = {"max_age_hours": values[4 if a else 5], "allow_express": a}
    return {"scope": scope, "revision": digest(body)[:8], **body}


class RuleShiftEnv(gym.Env):
    """Gymnasium-shaped text-tool environment; snapshot/restore are evaluator-only."""

    metadata: ClassVar[dict] = {"render_modes": ["ansi"]}

    def __init__(self, schedule: str = "single", split: str = "dev", tool_budget: int = 12):
        if schedule not in SCHEDULES or split not in ("dev", "validation", "test"):
            raise ValueError("Unknown schedule or split")
        if tool_budget < 1:
            raise ValueError("tool_budget must be positive")
        self.schedule, self.split, self.tool_budget = schedule, split, tool_budget
        self.action_space = spaces.Text(max_length=4096, charset="".join(chr(i) for i in range(32, 127)))
        self.observation_space = spaces.Text(
            max_length=20000, charset="".join(chr(i) for i in range(32, 127))
        )
        self.state: dict = {}
        self.events: list[dict] = []

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self.seed_value = seed if seed is not None else 101
        self.state = {
            "schema_version": 1,
            "seed": self.seed_value,
            "schedule": self.schedule,
            "split": self.split,
            "task_index": -1,
            "orders": {},
            "inventory": {"notebook": 100, "lamp": 100, "scarce": 0},
            "rules": {s: rules_for(self.split, s, "A") for s in SCOPES},
            "refunds": [],
            "shipments": [],
            "changes": [],
            "done": True,
            "calls": 0,
            "tool_budget": self.tool_budget,
            "task": None,
            "decision": None,
        }
        self.events = []
        self.initial_state = copy.deepcopy(self.state)
        self.task_start = None
        return json.dumps(self.observation()), {}

    def phases(self, index: int) -> dict:
        phases = dict.fromkeys(SCOPES, "A")
        if self.schedule in ("single", "multi") and index >= 3:
            phases["returns"] = "B"
        if self.schedule == "multi" and index >= 5:
            phases.update(fulfillment="B", changes="B")
        if self.schedule == "recurring" and 3 <= index < 6:
            phases = dict.fromkeys(SCOPES, "B")
        return phases

    def start_task(self, index: int | None = None) -> dict:
        if not self.state or not self.state["done"]:
            raise ValueError("Reset world or finish the current task first")
        index = self.state["task_index"] + 1 if index is None else index
        if index != self.state["task_index"] + 1 or not 0 <= index < 8:
            raise ValueError("Tasks must be started sequentially, indices 0..7")
        before = digest(self.state)
        previous_rules = copy.deepcopy(self.state["rules"])
        self.state["rules"] = {s: rules_for(self.split, s, p) for s, p in self.phases(index).items()}
        rng = random.Random(f"{self.seed_value}:{index}:{self.split}")
        scope = FAMILIES[index]
        template = rng.choice(TEMPLATES[scope][self.split])
        ra = rules_for(self.split, "returns", "A")["window_days"]
        rb = rules_for(self.split, "returns", "B")["window_days"]
        qa = rules_for(self.split, "fulfillment", "A")["max_quantity"]
        qb = rules_for(self.split, "fulfillment", "B")["max_quantity"]
        ca = rules_for(self.split, "changes", "A")["max_age_hours"]
        cb = rules_for(self.split, "changes", "B")["max_age_hours"]
        # Template families differ in which constraints are combined, not just names.
        composed = self.split in ("validation", "test") or template.endswith("edge")
        order_id = f"ORD-{index + 1:03d}"
        order = {
            "id": order_id,
            "sku": rng.choice(["notebook", "lamp"]),
            "quantity": rng.choice([1, qb + 1, qa + 1]) if scope == "fulfillment" else 1,
            "age_days": rng.choice([max(1, rb - 1), (ra + rb) // 2, ra + 2]),
            "age_hours": rng.choice([2, (ca + cb) // 2, ca + 2]),
            "opened": composed and rng.random() < 0.4,
            "destination": "island" if composed and rng.random() < 0.4 else "mainland",
            "service": "express" if composed and rng.random() < 0.4 else "standard",
            "address": "10 Original Street",
            "status": "delivered" if scope == "returns" else "pending",
        }
        if template.endswith("edge"):
            # Edge templates isolate the categorical constraint; basic isolates the numeric one.
            order.update(age_days=1, quantity=1, age_hours=2)
        if self.split == "validation":
            # Validation avoids simultaneous numeric and categorical violations.
            if order["age_days"] > rb:
                order["opened"] = False
            if order["quantity"] > qb:
                order["destination"] = "mainland"
            if order["age_hours"] > cb:
                order["service"] = "standard"
        if scope == "fulfillment" and composed and rng.random() < 0.15:
            order["sku"] = "scarce"
        self.state["orders"][order_id] = order
        requested_address = f"{20 + index} New Street"
        requests = {
            "returns": "Process this customer's return and refund if eligible; otherwise deny it.",
            "fulfillment": "Ship this customer's order if eligible and stocked; otherwise deny it.",
            "changes": f"Change this order's address to '{requested_address}' if eligible; otherwise deny it.",
        }
        self.state.update(
            task_index=index,
            calls=0,
            done=False,
            decision=None,
            task={
                "order_id": order_id,
                "scope": scope,
                "request": requests[scope],
                "requested_address": requested_address,
                "template": template,
            },
        )
        self.task_start = copy.deepcopy(self.state)
        self.events.append(
            {
                "kind": "start_task",
                "index": index,
                "before": before,
                "after": digest(self.state),
                "changed_scopes": [s for s in SCOPES if previous_rules[s] != self.state["rules"][s]],
                "observation": self.observation(),
            }
        )
        return self.observation()

    def observation(self) -> dict:
        if not self.state or self.state["task"] is None:
            return {"ready": True}
        t = self.state["task"]
        return {
            "task": {k: t[k] for k in ("order_id", "scope", "request")},
            "remaining_calls": max(0, self.tool_budget - self.state["calls"]),
            "done": self.state["done"],
        }

    def _permission(self, scope: str, order: dict) -> str | None:
        rule = self.state["rules"][scope]
        if scope == "returns":
            if order["age_days"] > rule["window_days"]:
                return "too_old"
            if order["opened"] and not rule["accept_opened"]:
                return "opened"
        elif scope == "fulfillment":
            if order["quantity"] > rule["max_quantity"]:
                return "max_quantity"
            if order["destination"] not in rule["destinations"]:
                return "destination"
            if self.state["inventory"][order["sku"]] < order["quantity"]:
                return "out_of_stock"
        else:
            if order["age_hours"] > rule["max_age_hours"]:
                return "locked"
            if order["service"] == "express" and not rule["allow_express"]:
                return "service_level"
        return None

    def _execute(self, action: Action) -> dict:
        name, a = action.tool, action.args
        fields = {t["tool"]: set(t["args"]) for t in TOOLS}[name]
        if set(a) != fields or any(not isinstance(v, str) for v in a.values()):
            return {"error": "invalid_arguments", "expected_fields": sorted(fields)}
        if name == "read_policy":
            if a["scope"] not in SCOPES:
                return {"error": "unknown_scope"}
            return {"policy": copy.deepcopy(self.state["rules"][a["scope"]])}
        if name == "inspect_stock":
            if a["sku"] not in self.state["inventory"]:
                return {"error": "unknown_sku"}
            return {"sku": a["sku"], "available": self.state["inventory"][a["sku"]]}
        if name == "finish":
            if a["decision"] not in ("complete", "deny"):
                return {"error": "invalid_decision"}
            self.state.update(done=True, decision=copy.deepcopy(a))
            return {"task_closed": True}
        if a["order_id"] not in self.state["orders"]:
            return {"error": "unknown_order"}
        order = self.state["orders"][a["order_id"]]
        if name == "inspect_order":
            return {"order": copy.deepcopy(order)}
        if a["order_id"] != self.state["task"]["order_id"]:
            return {"error": "out_of_task_scope"}
        scope = {"refund_order": "returns", "fulfill_order": "fulfillment", "change_order": "changes"}[name]
        if scope != self.state["task"]["scope"]:
            return {"error": "wrong_operation"}
        required = "delivered" if scope == "returns" else "pending"
        if order["status"] != required:
            return {"error": "invalid_status"}
        if scope == "changes" and any(c["order_id"] == order["id"] for c in self.state["changes"]):
            return {"error": "already_changed"}
        reason = self._permission(scope, order)
        if reason:
            return {"error": "policy_block" if reason != "out_of_stock" else "stock_block", "reason": reason}
        if scope == "returns":
            order["status"] = "refunded"
            self.state["inventory"][order["sku"]] += order["quantity"]
            self.state["refunds"].append({"order_id": order["id"], "units": order["quantity"]})
        elif scope == "fulfillment":
            order["status"] = "shipped"
            self.state["inventory"][order["sku"]] -= order["quantity"]
            self.state["shipments"].append({"order_id": order["id"], "units": order["quantity"]})
        else:
            if len(a["address"]) > 200 or not a["address"].strip():
                return {"error": "invalid_address"}
            order["address"] = a["address"]
            self.state["changes"].append({"order_id": order["id"], "address": a["address"]})
        return {"applied": True, "order": copy.deepcopy(order)}

    def step(self, action: str | dict):
        if not self.state or self.state["task"] is None or self.state["done"]:
            raise ValueError("No active task")
        before = digest(self.state)
        self.state["calls"] += 1
        try:
            parsed = (
                Action.model_validate_json(action)
                if isinstance(action, str)
                else Action.model_validate(action)
            )
            result = self._execute(parsed)
            serialized = parsed.model_dump()
        except (ValidationError, ValueError, TypeError):
            result = {"error": "invalid_action", "message": "Use one JSON object with tool and args."}
            serialized = action
        truncated = self.state["calls"] >= self.tool_budget and not self.state["done"]
        if truncated:
            self.state["done"] = True
        obs = {**self.observation(), "result": result}
        event = {
            "kind": "tool",
            "index": self.state["task_index"],
            "action": serialized,
            "observation": obs,
            "before": before,
            "after": digest(self.state),
        }
        self.events.append(event)
        from ruleshift.scoring import evaluate

        score = evaluate(self.task_start, self.state) if self.state["done"] else None
        return (
            json.dumps(obs),
            float(bool(score and score["success"])),
            self.state["done"] and not truncated,
            truncated,
            {},
        )

    def snapshot(self) -> dict:
        return copy.deepcopy(
            {
                "state": self.state,
                "events": self.events,
                "task_start": self.task_start,
                "initial_state": self.initial_state,
            }
        )

    def restore(self, snapshot: dict) -> None:
        snapshot = copy.deepcopy(snapshot)
        if snapshot["state"]["schema_version"] != 1:
            raise ValueError("Unsupported snapshot version")
        self.state, self.events, self.task_start = (
            snapshot["state"],
            snapshot["events"],
            snapshot["task_start"],
        )
        self.initial_state = snapshot["initial_state"]
        self.seed_value = self.state["seed"]
        self.schedule, self.split, self.tool_budget = (
            self.state[k] for k in ("schedule", "split", "tool_budget")
        )

    def render(self):
        return json.dumps(self.observation(), indent=2)


def replay(snapshot: dict) -> dict:
    """Replay recorded *world* actions; no model determinism is assumed."""
    initial = snapshot["initial_state"]
    env = RuleShiftEnv(initial["schedule"], initial["split"], initial["tool_budget"])
    env.reset(seed=initial["seed"])
    for event in snapshot["events"]:
        if digest(env.state) != event["before"]:
            raise ValueError("Replay pre-state mismatch")
        if event["kind"] == "start_task":
            env.start_task(event["index"])
        else:
            env.step(event["action"])
        if digest(env.state) != event["after"]:
            raise ValueError("Replay post-state mismatch")
        if env.events[-1]["observation"] != event["observation"]:
            raise ValueError("Replay observation mismatch")
    if env.snapshot() != snapshot:
        raise ValueError("Final snapshot mismatch")
    return {"verified": True, "events": len(env.events), "state_hash": digest(env.state)}
