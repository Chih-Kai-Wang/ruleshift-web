import json

import pytest

from ruleshift.web_batch import parse_decision, run_case, run_checkpointed


class RuleReader:
    """Explicit non-LLM control for testing driver and checkpoint semantics."""

    def __init__(self):
        self.calls = 0

    def generate(self, system, user, max_new_tokens=96):
        self.calls += 1
        prompt = json.loads(user)
        action = prompt["action"]
        policy = prompt["policy_evidence"][0]["policy"]
        order = prompt["task"].get("order", {})
        allowed = {
            "purchase": lambda: policy["eligible"],
            "refund": lambda: order["age_days"] <= policy["window_days"]
            and (not order["opened"] or policy["accept_opened"]),
            "ship": lambda: order["quantity"] <= policy["max_quantity"]
            and order["destination"] in policy["destinations"],
            "address": lambda: order["age_hours"] <= policy["max_age_hours"]
            and (order["service"] != "express" or policy["allow_express"]),
        }[action]()
        return {"text": json.dumps({"attempt": allowed, "reason": "ok" if allowed else "uncertain"}),
                "prompt_tokens": 20, "completion_tokens": 7, "seconds": 0.0}


def test_controlled_scenarios_keep_rejected_attempts_separate():
    reader = RuleReader()
    for action in ("purchase", "refund", "ship", "address"):
        for scenario in ("unchanged", "relevant_change", "unrelated_change", "reversion", "commit_race"):
            for strategy in ("retrieval", "always_refresh", "conditional_all", "source_dependent"):
                result = run_case(reader, action, scenario, strategy)
                assert result["final_correct"]
                assert result["invalid_commits"] == 0
                if scenario == "relevant_change" and strategy == "retrieval":
                    assert result["server_rejections"] == 1
                if scenario == "commit_race":
                    assert result["server_rejections"] == 1


def test_checkpoint_resume_does_not_duplicate_tasks(tmp_path):
    reader = RuleReader()
    cases = [("refund", "unchanged", "retrieval"), ("refund", "relevant_change", "retrieval")]
    info = {"backend": "deterministic_test_double", "revision": "fixed"}
    first = run_checkpointed(reader, tmp_path, info, cases)
    assert first == {"completed": 2, "planned": 2, "complete": True}
    calls = reader.calls
    assert run_checkpointed(reader, tmp_path, info, cases) == first
    assert reader.calls == calls
    with pytest.raises(ValueError, match="different model"):
        run_checkpointed(reader, tmp_path, {"revision": "changed"}, cases)


def test_decision_parser_rejects_prose_and_inconsistent_codes():
    assert parse_decision('{"attempt":true,"reason":"ok"}') == {"attempt": True, "reason": "ok"}
    assert parse_decision('{"attempt":false,"reason":"too_old"}') == {"attempt": False, "reason": "too_old"}
    assert parse_decision('{"attempt":true,"reason":"The policy allows it."}') is None
    assert parse_decision('{"attempt":true,"reason":"too_old"}') is None
    assert parse_decision('{"attempt":false,"reason":"ok"}') is None


def test_race_refusal_before_rule_change_is_not_counted_correct():
    class AlwaysDeny:
        def generate(self, system, user, max_new_tokens=96):
            return {"text": '{"attempt":false,"reason":"uncertain"}',
                    "prompt_tokens": 1, "completion_tokens": 1, "seconds": 0.0}

    result = run_case(AlwaysDeny(), "purchase", "commit_race", "source_dependent")
    assert result["initial_decision"] == {"attempt": False, "reason": "uncertain"}
    assert not result["committed"]
    assert not result["final_correct"]
