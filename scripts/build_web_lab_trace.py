"""Export a deterministic, self-contained browser replay of the v2 HTTP lab."""

from __future__ import annotations

import json
from pathlib import Path

from ruleshift.web_lab import Lab


def branch(kind: str) -> dict:
    lab = Lab()
    _, p1, etag1 = lab.read("discount", None)
    known = p1
    if kind == "unchanged":
        lab.read("discount", etag1)
    elif kind == "unrelated":
        lab.publish("shipping", {"free_threshold": 80})
        lab.read("discount", etag1)
    elif kind in ("cached", "conditional", "reload"):
        lab.publish("discount", {"eligible": False, "percent": 0})
        if kind != "cached":
            _, known, _ = lab.read("discount", etag1 if kind == "conditional" else None)
    elif kind == "reversion":
        lab.publish("discount", {"eligible": False, "percent": 0})
        lab.publish("discount", {"eligible": True, "percent": 10})
        lab.read("discount", etag1)
    elif kind == "race":
        lab.publish("discount", {"eligible": True, "percent": 5})
        _, known, _ = lab.read("discount", etag1)
        lab.publish("discount", {"eligible": False, "percent": 0})
    else:
        raise ValueError(kind)
    status, response = lab.purchase({"sku": "notebook", "request_discount": True,
                                     "expected_policy_revision": known["revision"]})
    check = lab.replay()
    assert check["verified"], check
    return {"execution_kind": "recorded_deterministic_lab_not_model", "intervention": kind,
            "outcome_status": status, "outcome": response, "snapshot": lab.snapshot(), "replay": check}


def main() -> None:
    lab = Lab()
    _, p1, etag1 = lab.read("discount", None)
    lab.read("discount", etag1)
    lab.publish("shipping", {"free_threshold": 80})
    lab.read("discount", etag1)
    lab.publish("discount", {"eligible": False, "percent": 0})
    _, p2, _ = lab.read("discount", etag1)
    lab.purchase({"sku": "notebook", "request_discount": True, "expected_policy_revision": p1["revision"]})
    lab.purchase({"sku": "notebook", "request_discount": True, "expected_policy_revision": p2["revision"]})
    lab.publish("discount", {"eligible": True, "percent": 5})
    lab.purchase({"sku": "notebook", "request_discount": True, "expected_policy_revision": p2["revision"]})
    _, p3, _ = lab.read("discount", None)
    lab.purchase({"sku": "notebook", "request_discount": True, "expected_policy_revision": p3["revision"]})
    lab.publish("discount", {"eligible": True, "percent": 10})
    lab.read("discount", None)
    retail = [
        ("returns", "RET-001", "refund", {"window_days": 14, "accept_opened": False},
         {"window_days": 30, "accept_opened": False}),
        ("fulfillment", "SHIP-001", "ship", {"max_quantity": 1, "destinations": ["mainland"]},
         {"max_quantity": 6, "destinations": ["mainland", "island"]}),
        ("changes", "ADDR-001", "address", {"max_age_hours": 18, "allow_express": False},
         {"max_age_hours": 72, "allow_express": True}),
    ]
    for scope, order_id, operation, restrictive, permissive in retail:
        _, prior, etag = lab.read(scope, None)
        lab.inspect_order(order_id)
        lab.publish(scope, restrictive)
        lab.operate(operation, order_id,
                    {"expected_policy_revision": prior["revision"], "address": "20 New Street"})
        _, current, _ = lab.read(scope, etag)
        lab.operate(operation, order_id,
                    {"expected_policy_revision": current["revision"], "address": "20 New Street"})
        lab.publish(scope, permissive)
        _, restored, _ = lab.read(scope, None)
        lab.operate(operation, order_id,
                    {"expected_policy_revision": restored["revision"], "address": "20 New Street"})
    replay = lab.replay()
    assert replay["verified"], replay
    payload = {
        "execution_kind": "recorded_deterministic_lab_not_model",
        "snapshot": lab.snapshot(), "replay": replay,
        "branches": {kind: branch(kind) for kind in
                     ("unchanged", "unrelated", "cached", "conditional", "reload", "reversion", "race")},
    }
    target = Path(__file__).parents[1] / "research" / "www2027" / "web_lab_trace.js"
    target.write_text("window.RULESHIFT_OFFLINE_TRACE = " + json.dumps(payload, sort_keys=True) + ";\n")
    print(f"Exported {replay['events']} verified events to {target}")


if __name__ == "__main__":
    main()
