"""Isolated v2 HTTP policy-publication and transaction experiment.

The site routes contain only public policy and transaction information.
Researcher routes expose the event log and must be bound to localhost; they
must never be offered to an evaluated agent or exposed through a public tunnel.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def revision(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()[:16]


INITIAL_POLICIES = {
    "discount": {"eligible": True, "percent": 10},
    "shipping": {"free_threshold": 50},
    "returns": {"window_days": 30, "accept_opened": False},
    "fulfillment": {"max_quantity": 6, "destinations": ["mainland", "island"]},
    "changes": {"max_age_hours": 72, "allow_express": True},
}
INITIAL_ORDERS = {
    "RET-001": {"id": "RET-001", "kind": "returns", "sku": "notebook", "quantity": 1,
                "status": "delivered", "age_days": 20, "opened": False},
    "SHIP-001": {"id": "SHIP-001", "kind": "fulfillment", "sku": "lamp", "quantity": 2,
                 "status": "pending", "destination": "island"},
    "ADDR-001": {"id": "ADDR-001", "kind": "changes", "sku": "lamp", "quantity": 1,
                 "status": "pending", "age_hours": 24, "service": "express", "address": "10 Original Street"},
}
LAB_FILES = Path(__file__).parents[2] / "research" / "www2027"


def matches_if_none_match(value: str | None, etag: str) -> bool:
    if value is None:
        return False
    # If-None-Match uses weak comparison for GET. Our origin emits strong ETags.
    return any(tag.strip().removeprefix("W/") in (etag, "*") for tag in value.split(","))


class Publish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["discount", "shipping", "returns", "fulfillment", "changes"]
    rule: dict


class Purchase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: Literal["notebook"] = "notebook"
    request_discount: bool = True
    expected_policy_revision: str = Field(min_length=16, max_length=16)


class OrderOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_policy_revision: str = Field(min_length=16, max_length=16)
    address: str | None = Field(default=None, max_length=200)


class Lab:
    def __init__(self, initial_policies: dict | None = None, initial_orders: dict | None = None):
        self.lock = threading.RLock()
        self.initial_policies = copy.deepcopy(
            INITIAL_POLICIES if initial_policies is None else initial_policies
        )
        self.initial_orders = copy.deepcopy(
            INITIAL_ORDERS if initial_orders is None else initial_orders
        )
        self.policies = copy.deepcopy(self.initial_policies)
        self.purchases: list[dict] = []
        self.orders = copy.deepcopy(self.initial_orders)
        self.inventory = {"notebook": 100, "lamp": 100}
        self.events: list[dict] = []

    def state(self) -> dict:
        return {"policies": copy.deepcopy(self.policies), "purchases": copy.deepcopy(self.purchases),
                "orders": copy.deepcopy(self.orders), "inventory": copy.deepcopy(self.inventory)}

    def _record(self, kind: str, request: dict, status: int, response: dict | None) -> None:
        self.events.append(
            {
                "seq": len(self.events),
                "kind": kind,
                "request": copy.deepcopy(request),
                "status": status,
                "response": copy.deepcopy(response),
                "state_hash": revision(self.state()),
            }
        )

    def read(self, scope: str, if_none_match: str | None) -> tuple[int, dict | None, str]:
        with self.lock:
            if scope not in self.policies:
                raise KeyError(scope)
            body = {"scope": scope, "revision": revision(self.policies[scope]), **self.policies[scope]}
            etag = '"' + revision(body) + '"'
            status = 304 if matches_if_none_match(if_none_match, etag) else 200
            response = None if status == 304 else body
            self._record(
                "read", {"scope": scope, "if_none_match": if_none_match}, status, response
            )
            return status, response, etag

    def publish(self, scope: str, rule: dict) -> dict:
        with self.lock:
            if scope == "discount":
                if set(rule) != {"eligible", "percent"} or not isinstance(rule["eligible"], bool):
                    raise ValueError("Invalid discount policy")
                if type(rule["percent"]) is not int or not 0 <= rule["percent"] <= 100:
                    raise ValueError("Invalid discount percent")
            elif scope == "shipping":
                if set(rule) != {"free_threshold"} or type(rule["free_threshold"]) is not int:
                    raise ValueError("Invalid shipping policy")
                if rule["free_threshold"] < 0:
                    raise ValueError("Invalid shipping threshold")
            elif scope == "returns":
                if set(rule) != {"window_days", "accept_opened"}:
                    raise ValueError("Invalid return policy")
                if type(rule["window_days"]) is not int or rule["window_days"] < 0:
                    raise ValueError("Invalid return window")
                if type(rule["accept_opened"]) is not bool:
                    raise ValueError("Invalid opened-item rule")
            elif scope == "fulfillment":
                if set(rule) != {"max_quantity", "destinations"}:
                    raise ValueError("Invalid fulfillment policy")
                if type(rule["max_quantity"]) is not int or rule["max_quantity"] < 1:
                    raise ValueError("Invalid maximum quantity")
                if not isinstance(rule["destinations"], list) or not rule["destinations"]:
                    raise ValueError("Invalid destinations")
                if any(d not in ("mainland", "island") for d in rule["destinations"]):
                    raise ValueError("Invalid destination")
            elif scope == "changes":
                if set(rule) != {"max_age_hours", "allow_express"}:
                    raise ValueError("Invalid address-change policy")
                if type(rule["max_age_hours"]) is not int or rule["max_age_hours"] < 0:
                    raise ValueError("Invalid address-change age")
                if type(rule["allow_express"]) is not bool:
                    raise ValueError("Invalid express rule")
            else:
                raise KeyError(scope)
            self.policies[scope] = copy.deepcopy(rule)
            body = {"scope": scope, "revision": revision(rule), **rule}
            self._record("publish", {"scope": scope, "rule": rule}, 200, body)
            return body

    def inspect_order(self, order_id: str) -> dict:
        with self.lock:
            if order_id not in self.orders:
                raise KeyError(order_id)
            body = {"order": copy.deepcopy(self.orders[order_id])}
            self._record("inspect_order", {"order_id": order_id}, 200, body)
            return body

    def operate(self, operation: str, order_id: str, request: dict) -> tuple[int, dict]:
        with self.lock:
            if order_id not in self.orders:
                raise KeyError(order_id)
            order = self.orders[order_id]
            scope = {"refund": "returns", "ship": "fulfillment", "address": "changes"}[operation]
            if order["kind"] != scope:
                status, body = 409, {"error": "wrong_operation"}
            elif request["expected_policy_revision"] != revision(self.policies[scope]):
                status, body = 409, {"error": "policy_revision_changed"}
            elif order["status"] != ("delivered" if scope == "returns" else "pending"):
                status, body = 409, {"error": "invalid_status"}
            else:
                policy = self.policies[scope]
                reason = None
                if scope == "returns":
                    if order["age_days"] > policy["window_days"]:
                        reason = "too_old"
                    elif order["opened"] and not policy["accept_opened"]:
                        reason = "opened"
                elif scope == "fulfillment":
                    if order["quantity"] > policy["max_quantity"]:
                        reason = "max_quantity"
                    elif order["destination"] not in policy["destinations"]:
                        reason = "destination"
                    elif self.inventory[order["sku"]] < order["quantity"]:
                        reason = "out_of_stock"
                else:
                    if order["age_hours"] > policy["max_age_hours"]:
                        reason = "locked"
                    elif order["service"] == "express" and not policy["allow_express"]:
                        reason = "service_level"
                    elif not request.get("address") or not request["address"].strip():
                        reason = "invalid_address"
                if reason:
                    status, body = 409, {"error": "policy_block", "reason": reason}
                else:
                    if scope == "returns":
                        order["status"] = "refunded"
                        self.inventory[order["sku"]] += order["quantity"]
                    elif scope == "fulfillment":
                        order["status"] = "shipped"
                        self.inventory[order["sku"]] -= order["quantity"]
                    else:
                        order["address"] = request["address"]
                        order["status"] = "address_changed"
                    status, body = 200, {"order": copy.deepcopy(order), "policy_revision": revision(policy)}
            self._record("operate", {"operation": operation, "order_id": order_id, **request}, status, body)
            return status, body

    def purchase(self, request: dict) -> tuple[int, dict]:
        with self.lock:
            current = self.policies["discount"]
            current_revision = revision(current)
            if request["expected_policy_revision"] != current_revision:
                status, body = 409, {"error": "policy_revision_changed"}
            elif request["request_discount"] and not current["eligible"]:
                status, body = 409, {"error": "policy_block", "reason": "discount_ineligible"}
            else:
                discount = current["percent"] if request["request_discount"] else 0
                order = {
                    "id": f"BUY-{len(self.purchases) + 1:03d}",
                    "sku": request["sku"],
                    "list_price": 100,
                    "discount_percent": discount,
                    "paid": 100 - discount,
                    "policy_revision": current_revision,
                }
                self.purchases.append(order)
                status, body = 201, {"purchase": copy.deepcopy(order)}
            self._record("purchase", request, status, body)
            return status, body

    def snapshot(self) -> dict:
        with self.lock:
            result = {"initial_policies": copy.deepcopy(self.initial_policies),
                      "state": self.state(), "events": copy.deepcopy(self.events)}
            if self.initial_orders != INITIAL_ORDERS:
                result["initial_orders"] = copy.deepcopy(self.initial_orders)
            return result

    def replay(self) -> dict:
        return verify_snapshot(self.snapshot())


def verify_snapshot(original: dict) -> dict:
    """Re-execute an exported trace and compare every response and state hash."""
    initial_policies = original.get("initial_policies")
    initial_orders = original.get("initial_orders", INITIAL_ORDERS)
    if not isinstance(initial_policies, dict) or set(initial_policies) != set(INITIAL_POLICIES):
        return {"verified": False, "error": "initial_policy_mismatch"}
    if not isinstance(initial_orders, dict):
        return {"verified": False, "error": "initial_order_mismatch"}
    if not isinstance(original.get("events"), list):
        return {"verified": False, "error": "missing_events"}
    fresh = Lab(initial_policies, initial_orders)
    for index, expected in enumerate(original["events"]):
        try:
            kind, request = expected["kind"], expected["request"]
            if kind == "read":
                fresh.read(request["scope"], request["if_none_match"])
            elif kind == "publish":
                fresh.publish(request["scope"], request["rule"])
            elif kind == "purchase":
                fresh.purchase(request)
            elif kind == "inspect_order":
                fresh.inspect_order(request["order_id"])
            elif kind == "operate":
                fresh.operate(request["operation"], request["order_id"],
                              {k: request[k] for k in ("expected_policy_revision", "address")})
            else:
                return {"verified": False, "error": "unknown_event", "seq": index}
        except (KeyError, TypeError, ValueError, IndexError):
            return {"verified": False, "error": "invalid_event", "seq": index}
        if fresh.events[-1] != expected:
            return {"verified": False, "error": "event_mismatch", "seq": index}
    if "state" not in original:
        return {"verified": False, "error": "missing_state"}
    verified = fresh.state() == original["state"]
    return {"verified": verified, "events": len(fresh.events),
            "final_state_hash": revision(fresh.state()),
            **({} if verified else {"error": "final_state_mismatch"})}


def create_app(lab: Lab | None = None) -> FastAPI:
    lab = Lab() if lab is None else lab
    app = FastAPI(title="RuleShift-Web v2 policy laboratory", version="0.2.0")

    @app.get("/lab/")
    def lab_page():
        return FileResponse(LAB_FILES / "web_lab_ui.html", media_type="text/html")

    @app.get("/lab/web_lab_trace.js")
    def offline_trace():
        return FileResponse(LAB_FILES / "web_lab_trace.js", media_type="text/javascript")

    @app.get("/lab/web_model_trace.js")
    def offline_model_trace():
        return FileResponse(LAB_FILES / "web_model_trace.js", media_type="text/javascript")

    @app.get("/site/policies/{scope}")
    def get_policy(scope: str, if_none_match: str | None = Header(default=None)):
        try:
            status, body, etag = lab.read(scope, if_none_match)
        except KeyError as exc:
            raise HTTPException(404, "Policy not found") from exc
        headers = {"ETag": etag, "Cache-Control": "public, max-age=120"}
        if status == 304:
            return Response(status_code=304, headers=headers)
        return JSONResponse(body, headers=headers)

    @app.post("/site/purchases")
    def submit_purchase(request: Purchase):
        status, body = lab.purchase(request.model_dump())
        return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})

    @app.get("/site/orders/{order_id}")
    def inspect_order(order_id: str):
        try:
            return lab.inspect_order(order_id)
        except KeyError as exc:
            raise HTTPException(404, "Order not found") from exc

    @app.post("/site/orders/{order_id}/{operation}")
    def submit_operation(order_id: str, operation: Literal["refund", "ship", "address"], request: OrderOperation):
        try:
            status, body = lab.operate(operation, order_id, request.model_dump())
        except KeyError as exc:
            raise HTTPException(404, "Order not found") from exc
        return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})

    @app.post("/research/publish")
    def publish_policy(request: Publish):
        try:
            return lab.publish(request.scope, request.rule)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/research/reset")
    def reset():
        nonlocal lab
        lab = Lab(lab.initial_policies, lab.initial_orders)
        return lab.snapshot()

    @app.get("/research/snapshot")
    def snapshot():
        return lab.snapshot()

    @app.get("/research/replay")
    def replay():
        return lab.replay()

    return app


app = create_app()
