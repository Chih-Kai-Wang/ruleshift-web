from collections import Counter

import pytest

from ruleshift.web_schedule import balanced_schedule
from ruleshift.web_streams import make_split


def test_formal_schedule_is_complete_balanced_and_mirrored():
    streams = make_split("test", 20260928, 10)
    strategies = ("retrieval", "always_refresh", "conditional_all",
                  "v1_selective", "source_dependent")
    first = balanced_schedule(streams, strategies, 20261001, 0)
    second = balanced_schedule(streams, strategies, 20261001, 1)
    control = balanced_schedule(streams, strategies, 20261001, 2)
    expected = {(stream.stream_id, strategy) for stream in streams for strategy in strategies}
    assert len(first) == len(second) == len(control) == len(expected) == 200
    assert set(first) == set(second) == set(control) == expected
    assert first == balanced_schedule(streams, strategies, 20261001, 0)
    for schedule in (first, second, control):
        positions = Counter(strategy for index, (_stream, strategy) in enumerate(schedule)
                            if index % 5 == 0)
        assert set(positions.values()) == {8}
    assert first != second


def test_schedule_rejects_imbalanced_or_duplicate_matrix():
    streams = make_split("development", 20260928, 2)
    with pytest.raises(ValueError, match="divisible"):
        balanced_schedule(streams, ("a", "b", "c"), 1, 0)
    with pytest.raises(ValueError, match="Duplicate strategy"):
        balanced_schedule(streams, ("a", "a"), 1, 0)
