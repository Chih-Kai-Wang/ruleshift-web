import copy
import json

import pytest

from ruleshift.scoring import evaluate, reference_actions, restrictions
from ruleshift.world import RuleShiftEnv, replay


@pytest.mark.parametrize("split", ["dev", "validation", "test"])
@pytest.mark.parametrize("schedule", ["stable", "single", "multi", "recurring"])
def test_reference_solves_and_replays(split, schedule):
    for seed in [101, 202, 303, 404, 505, 1, 7]:
        env = RuleShiftEnv(schedule, split)
        env.reset(seed=seed)
        for i in range(8):
            env.start_task()
            for action in reference_actions(env.task_start):
                env.step(action)
            assert evaluate(env.task_start, env.state)["success"], (split, schedule, seed, i)
            assert min(env.state["inventory"].values()) >= 0
        assert replay(env.snapshot())["verified"]


def test_restore_is_exact_and_isolated():
    env = RuleShiftEnv()
    env.reset(seed=101)
    env.start_task()
    snapshot = env.snapshot()
    observation = env.step({"tool": "inspect_order", "args": {"order_id": "ORD-001"}})
    other = RuleShiftEnv("recurring", "test", 3)
    other.restore(snapshot)
    assert other.step({"tool": "inspect_order", "args": {"order_id": "ORD-001"}}) == observation
    assert other.snapshot() == env.snapshot()
    snapshot["state"]["inventory"]["lamp"] = -100
    assert other.state["inventory"]["lamp"] >= 0


def test_claiming_success_does_not_do_work():
    for seed in range(10):
        env = RuleShiftEnv()
        env.reset(seed=seed)
        env.start_task()
        env.step({"tool": "finish", "args": {"decision": "complete", "reason": "ok"}})
        assert not evaluate(env.task_start, env.state)["success"]


def test_denying_eligible_task_is_failure():
    env = RuleShiftEnv()
    env.reset(seed=101)
    for _ in range(8):
        env.start_task()
        eligible = not restrictions(env.task_start)
        env.step({"tool": "finish", "args": {"decision": "deny", "reason": "too_old"}})
        if eligible:
            assert not evaluate(env.task_start, env.state)["success"]


def test_duplicate_effects_are_rejected():
    found = False
    for seed in range(20):
        env = RuleShiftEnv()
        env.reset(seed=seed)
        env.start_task()
        actions = reference_actions(env.task_start)
        if len(actions) == 1:
            continue
        found = True
        env.step(actions[0])
        business = copy.deepcopy({k: env.state[k] for k in ("inventory", "refunds", "orders")})
        obs, *_ = env.step(actions[0])
        assert json.loads(obs)["result"]["error"] == "invalid_status"
        assert {k: env.state[k] for k in business} == business
    assert found


def test_illegal_actions_consume_budget_without_effects():
    env = RuleShiftEnv(tool_budget=2)
    env.reset(seed=101)
    env.start_task()
    before = copy.deepcopy(env.state["orders"])
    _, reward, done, truncated, _ = env.step({"tool": "refund_order", "args": {"order_id": "absent"}})
    assert not done and not truncated and reward == 0
    _, reward, done, truncated, _ = env.step("NOT JSON")
    assert truncated and reward == 0
    assert env.state["orders"] == before
    assert replay(env.snapshot())["verified"]


def test_agent_observation_has_no_research_truth():
    env = RuleShiftEnv("recurring", "test")
    env.reset(seed=901234567)
    for _ in range(8):
        obs = env.start_task()
        serialized = json.dumps(obs)
        for forbidden in ["901234567", "recurring", "template", "changed_scopes", "revision", "window_days"]:
            assert forbidden not in serialized
        assert set(obs) == {"task", "remaining_calls", "done"}
        env.step({"tool": "finish", "args": {"decision": "deny", "reason": "too_old"}})


def test_enforced_rule_errors_do_not_change_business_state():
    for seed in range(20):
        env = RuleShiftEnv("recurring", "test")
        env.reset(seed=seed)
        for i in range(8):
            env.start_task()
            if restrictions(env.task_start):
                t = env.state["task"]
                name = {"returns": "refund_order", "fulfillment": "fulfill_order", "changes": "change_order"}[
                    t["scope"]
                ]
                args = {"order_id": t["order_id"]}
                if t["scope"] == "changes":
                    args["address"] = t["requested_address"]
                before = copy.deepcopy(
                    [env.state[k] for k in ("orders", "inventory", "refunds", "shipments", "changes")]
                )
                obs, *_ = env.step({"tool": name, "args": args})
                assert json.loads(obs)["result"]["error"] in ("policy_block", "stock_block")
                assert [
                    env.state[k] for k in ("orders", "inventory", "refunds", "shipments", "changes")
                ] == before
            for a in reference_actions(env.task_start):
                env.step(a)


def test_replay_detects_tampering():
    env = RuleShiftEnv()
    env.reset(seed=1)
    env.start_task()
    env.step({"tool": "finish", "args": {"decision": "deny", "reason": "too_old"}})
    snapshot = env.snapshot()
    snapshot["events"][1]["observation"]["result"] = {"forged": True}
    with pytest.raises(ValueError, match="observation"):
        replay(snapshot)
