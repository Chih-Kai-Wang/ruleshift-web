"""Public-evidence-only deterministic controller for the v2 development lab.

This is a strong non-LLM control, not an agent memory method. It receives the
same serialized task and policy evidence as a model and has no Lab access.
"""

from __future__ import annotations

import json
import time


class DeterministicController:
    def __init__(self) -> None:
        self.provenance = {"backend": "deterministic_public_evidence", "revision": "v2-g2-1"}

    def generate(self, system: str, user: str, max_new_tokens: int = 96) -> dict:
        started = time.perf_counter()
        prompt = json.loads(user)
        action = prompt["action"]
        source = prompt["policy_evidence"][0]
        policy = source["policy"]
        order = prompt["task"].get("order", {})
        reason = "ok"
        if action == "purchase":
            if not policy["eligible"]:
                reason = "discount_ineligible"
        elif action == "refund":
            if order["age_days"] > policy["window_days"]:
                reason = "too_old"
            elif order["opened"] and not policy["accept_opened"]:
                reason = "opened"
        elif action == "ship":
            if order["quantity"] > policy["max_quantity"]:
                reason = "max_quantity"
            elif order["destination"] not in policy["destinations"]:
                reason = "destination"
        elif action == "address":
            if order["age_hours"] > policy["max_age_hours"]:
                reason = "locked"
            elif order["service"] == "express" and not policy["allow_express"]:
                reason = "service_level"
        else:
            raise ValueError(f"Unknown action {action}")
        answer = json.dumps({"attempt": reason == "ok", "reason": reason}, separators=(",", ":"))
        return {
            "text": answer,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "seconds": time.perf_counter() - started,
        }
