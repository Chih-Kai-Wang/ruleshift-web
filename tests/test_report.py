import copy

import pytest

from ruleshift.report import summarize
from ruleshift.scoring import evaluate, reference_actions
from ruleshift.world import RuleShiftEnv


def records(schedule="recurring"):
    rows = []
    for seed in (101, 202):
        for policy in ("refresh", "selective"):
            env = RuleShiftEnv(schedule, "dev")
            env.reset(seed=seed)
            for index in range(8):
                env.start_task()
                for action in reference_actions(env.task_start):
                    env.step(action)
                rows.append(
                    {
                        "schedule": schedule,
                        "seed": seed,
                        "policy": policy,
                        "task_index": index,
                        "snapshot": env.snapshot(),
                        "score": evaluate(env.task_start, env.state),
                        "stale_consistent_error": False,
                        "cost": dict.fromkeys(
                            (
                                "tool_calls",
                                "policy_reads",
                                "illegal_attempts",
                                "prompt_tokens",
                                "completion_tokens",
                                "wall_seconds",
                                "model_seconds",
                            ),
                            1,
                        ),
                    }
                )
    return rows


def test_bootstrap_uses_paired_streams_and_keeps_failed_tasks():
    rows = records()
    for row in rows:
        if row["policy"] == "selective" and row["task_index"] == 3:
            row["score"]["success"] = False
    result = summarize(rows, 32)
    assert result["complete"]
    comparison = result["paired_comparison"]
    assert comparison["n_pairs"] == 2  # not 32 dependent observations
    assert comparison["mean_success_difference"] == pytest.approx(-1 / 8)
    assert comparison["bootstrap_95_percent_interval"] == [-1 / 8, -1 / 8]
    selective = next(row for row in result["policies"] if row["policy"] == "selective")
    assert (selective["successes"], selective["n"]) == (14, 16)
    partial = summarize(rows[:-1], 32)
    assert not partial["complete"] and partial["paired_comparison"]["n_pairs"] == 1


def test_recovery_does_not_drop_unobserved_scopes_and_respects_recurrence():
    rows = records()
    result = summarize(rows, 32)
    unobserved = [r for r in result["recovery"] if r["scope"] == "fulfillment" and r["change_at"] == 6]
    assert len(unobserved) == 4
    assert all(
        r["censored"] and r["affected_tasks_observed"] == 0 and r["tasks_to_first_success"] is None
        for r in unobserved
    )
    changed_returns = [r for r in result["recovery"] if r["scope"] == "returns" and r["change_at"] == 3]
    assert all(r["tasks_to_first_success"] == 1 for r in changed_returns)
    # A scope whose original rule returned has still experienced a change.
    assert all(row["unchanged_scope_n"] == 6 for row in result["policies"])
    stable = summarize(records("stable"), 32)
    assert stable["recovery"] == []
    assert all(row["unchanged_scope_n"] == 16 for row in stable["policies"])


def test_report_does_not_mutate_input_records():
    rows = records()
    before = copy.deepcopy(rows)
    summarize(rows, 32)
    assert rows == before
