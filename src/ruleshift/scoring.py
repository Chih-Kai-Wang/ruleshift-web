"""Independent evaluator. Does not call the world's action permission implementation."""

from __future__ import annotations

import copy


def restrictions(start: dict) -> list[str]:
    task = start["task"]
    order = start["orders"][task["order_id"]]
    rule = start["rules"][task["scope"]]
    checks = {
        "returns": lambda: [
            ("too_old", order["age_days"] > rule["window_days"]),
            ("opened", bool(order["opened"]) and not rule["accept_opened"]),
        ],
        "fulfillment": lambda: [
            ("max_quantity", order["quantity"] > rule["max_quantity"]),
            ("destination", order["destination"] not in rule["destinations"]),
            ("out_of_stock", start["inventory"][order["sku"]] < order["quantity"]),
        ],
        "changes": lambda: [
            ("locked", order["age_hours"] > rule["max_age_hours"]),
            ("service_level", order["service"] == "express" and not rule["allow_express"]),
        ],
    }
    return [name for name, blocked in checks[task["scope"]]() if blocked]


def evaluate(start: dict, end: dict) -> dict:
    reasons = restrictions(start)
    task, decision = start["task"], end.get("decision")
    oid, scope = task["order_id"], task["scope"]
    # Compare the complete business state, not only a model-written success flag.
    fields = ("orders", "inventory", "refunds", "shipments", "changes")
    expected = {k: copy.deepcopy(start[k]) for k in fields}
    if not reasons:
        order = expected["orders"][oid]
        if scope == "returns":
            order["status"] = "refunded"
            expected["inventory"][order["sku"]] += order["quantity"]
            expected["refunds"].append({"order_id": oid, "units": order["quantity"]})
        elif scope == "fulfillment":
            order["status"] = "shipped"
            expected["inventory"][order["sku"]] -= order["quantity"]
            expected["shipments"].append({"order_id": oid, "units": order["quantity"]})
        else:
            order["address"] = task["requested_address"]
            expected["changes"].append({"order_id": oid, "address": task["requested_address"]})
    state_ok = all(end[k] == v for k, v in expected.items())
    decision_ok = bool(
        decision
        and (
            (not reasons and decision["decision"] == "complete")
            or (reasons and decision["decision"] == "deny" and decision["reason"] in reasons)
        )
    )
    return {
        "success": bool(state_ok and decision_ok),
        "state_ok": state_ok,
        "decision_ok": decision_ok,
        "expected_decision": "deny" if reasons else "complete",
        "valid_reasons": reasons,
        "scope": scope,
        "order_id": oid,
    }


def reference_actions(start: dict) -> list[dict]:
    """Privileged evaluator oracle: NEVER a model baseline or an agent tool."""
    task = start["task"]
    reasons = restrictions(start)
    if reasons:
        return [{"tool": "finish", "args": {"decision": "deny", "reason": reasons[0]}}]
    tool = {"returns": "refund_order", "fulfillment": "fulfill_order", "changes": "change_order"}[
        task["scope"]
    ]
    args = {"order_id": task["order_id"]}
    if task["scope"] == "changes":
        args["address"] = task["requested_address"]
    return [
        {"tool": tool, "args": args},
        {"tool": "finish", "args": {"decision": "complete", "reason": "ok"}},
    ]
