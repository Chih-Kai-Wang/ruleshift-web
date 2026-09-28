import json

from ruleshift.web_lab import Lab
from ruleshift.web_streams import ACTIONS, SCENARIOS, make_split, make_stream, semantic_signature


def test_candidate_stream_matrix_is_sequential_and_split_separated():
    development = make_split("development", 20260928, 2)
    formal = make_split("test", 20260928, 10)
    assert len(development) == 8
    assert len(formal) == 40
    assert len(formal) * 8 * 5 * 2 == 3200
    assert {s.stream_id for s in development}.isdisjoint(s.stream_id for s in formal)
    assert {s.sha256() for s in development}.isdisjoint(s.sha256() for s in formal)
    assert make_split("test", 20260928, 10) == formal

    def semantic_signature(stream):
        # Ignore stream IDs and order IDs; a different seed/identifier alone
        # must not pass the held-out separation check.
        orders = []
        for task in stream.tasks:
            order = dict(task.get("order", {}))
            order.pop("id", None)
            orders.append(order)
        return json.dumps([stream.scenario, stream.action, stream.initial_rule,
                           stream.changed_rule, orders, stream.publications],
                          sort_keys=True)

    dev_signatures = {semantic_signature(s) for s in development}
    test_signatures = {semantic_signature(s) for s in formal}
    assert len(test_signatures) == len(formal)
    assert dev_signatures.isdisjoint(test_signatures)
    for scenario in SCENARIOS:
        cell = [s for s in formal if s.scenario == scenario]
        assert len(cell) == 10
        assert {s.action for s in cell} == set(ACTIONS)
        for stream in cell:
            assert len(stream.tasks) == 8
            assert len({t["request_id"] for t in stream.tasks}) == 8
            assert all(0 < event["before_step"] < 8 for event in stream.publications)
            assert all(event["scope"] != "shipping" for event in stream.publications
                       if scenario in ("relevant_change", "reversion") and stream.action != "ship")


def test_candidate_changes_have_expected_boundaries():
    streams = make_split("test", 20260928, 10)
    assert all(not s.publications for s in streams if s.scenario == "unchanged")
    assert all(len(s.publications) == 1 for s in streams
               if s.scenario in ("relevant_change", "unrelated_change"))
    assert all([p["before_step"] for p in s.publications] == [3, 6]
               for s in streams if s.scenario == "reversion")


def test_candidate_policies_are_valid_and_change_eligibility():
    for stream in make_split("test", 20260928, 10):
        lab = Lab()
        scope = {"purchase": "discount", "refund": "returns",
                 "ship": "fulfillment", "address": "changes"}[stream.action]
        lab.publish(scope, stream.initial_rule)
        lab.publish(scope, stream.changed_rule)
        for task in stream.tasks:
            if stream.action == "purchase":
                assert stream.initial_rule["eligible"]
                assert not stream.changed_rule["eligible"]
            elif stream.action == "refund":
                age = task["order"]["age_days"]
                assert stream.changed_rule["window_days"] < age <= stream.initial_rule["window_days"]
            elif stream.action == "ship":
                quantity = task["order"]["quantity"]
                assert stream.changed_rule["max_quantity"] < quantity <= stream.initial_rule["max_quantity"]
            else:
                age = task["order"]["age_hours"]
                assert stream.changed_rule["max_age_hours"] < age <= stream.initial_rule["max_age_hours"]


def test_new_formal_seed_is_semantically_disjoint_from_development_preflight():
    development = [make_stream("development", scenario, index, 20260928)
                   for index, scenario in enumerate(SCENARIOS)]
    formal = make_split("test", 20261003, 10)
    assert {semantic_signature(s) for s in development}.isdisjoint(
        semantic_signature(s) for s in formal
    )
