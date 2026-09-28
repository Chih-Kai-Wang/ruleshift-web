import json

from ruleshift.agents import Memory, build_user, parse_action


class TokenCounter:
    def tokens(self, text):
        return len(text)


def test_ttl_and_scope():
    mem = Memory("ttl")
    mem.observe("returns", {"window_days": 30}, 0, "observed")
    assert mem.visible("returns", 1, TokenCounter())
    assert not mem.visible("returns", 2, TokenCounter())
    assert not mem.visible("changes", 0, TokenCounter())


def test_memory_budget_and_none():
    mem = Memory("retrieval")
    mem.observe("returns", {"long": "x" * 2000}, 0, "observed")
    assert not mem.visible("returns", 0, TokenCounter())
    none = Memory("none")
    none.observe("returns", {"window_days": 30}, 0, "observed")
    assert none.entries == {}


def test_prompt_excludes_timing_and_evaluator_truth():
    obs = {
        "task": {"scope": "returns"},
        "remaining_calls": 10,
        "done": False,
        "hidden": "ANSWER_SECRET_927",
        "future": "CHANGE_SECRET_328",
    }
    history = [
        {
            "action": {"tool": "inspect_order"},
            "result": {"order": {}},
            "tool_seconds": 0.001923,
            "origin": "model",
            "hidden": "SECRET",
        }
    ]
    prompt = build_user(obs, [], history, [])
    assert "SECRET" not in prompt and "tool_seconds" not in prompt and "origin" not in prompt
    history[0]["tool_seconds"] = 5000
    assert prompt == build_user(obs, [], history, [])
    assert set(json.loads(prompt)) == {"tools", "task_state", "memory", "this_task_history"}


def test_parser_does_not_repair_outputs():
    assert parse_action('{"tool":"finish","args":{}}') == {"tool": "finish", "args": {}}
    assert isinstance(parse_action('Here is the answer: {"tool":"finish"}'), str)
