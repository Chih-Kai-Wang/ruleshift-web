"""Recorded, balanced order for the paired G3 stream/strategy matrix."""

from __future__ import annotations

import random

from ruleshift.web_streams import StreamSpec


def balanced_schedule(streams: tuple[StreamSpec, ...], strategies: tuple[str, ...],
                      seed: int, model_slot: int) -> tuple[tuple[str, str], ...]:
    """Shuffle streams and rotate strategies so each position is balanced.

    `model_slot=1` mirrors strategy positions relative to model_slot=0.
    `model_slot=2` is the separately counted deterministic control.
    Loading the two models in separate sessions is still a temporal limitation.
    """
    if not streams or not strategies or model_slot not in (0, 1, 2):
        raise ValueError("Invalid schedule inputs")
    if len({stream.stream_id for stream in streams}) != len(streams):
        raise ValueError("Duplicate stream ID")
    if len(set(strategies)) != len(strategies):
        raise ValueError("Duplicate strategy")
    if len(streams) % len(strategies):
        raise ValueError("Stream count must be divisible by strategy count")
    order = list(streams)
    random.Random(seed).shuffle(order)
    schedule = []
    for index, stream in enumerate(order):
        rotation = index % len(strategies)
        strategy_order = [strategies[(rotation + position) % len(strategies)]
                          for position in range(len(strategies))]
        if model_slot == 1:
            strategy_order.reverse()
        schedule.extend((stream.stream_id, strategy) for strategy in strategy_order)
    return tuple(schedule)
