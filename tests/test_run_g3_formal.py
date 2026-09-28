import hashlib
from pathlib import Path

import pytest

import scripts.run_g3_colab_formal as formal_script
from ruleshift.cuda_model import CudaModel
from ruleshift.web_stream_runner import implementation_sha256
from ruleshift.web_streams import make_split
from scripts.run_g3_colab_formal import PINNED, STRATEGIES, validate_frozen_protocol


def _synthetic_protocol():
    streams = make_split("test", 20260928, 10)
    return {
        "kind": "RuleShift-Web-G3", "status": "frozen",
        "streams_per_scenario": 10, "stream_seed": 20260928,
        "schedule_seed": 20261001,
        "stream_sha256": [s.sha256() for s in streams],
        "strategies": list(STRATEGIES), "model_ids": list(PINNED),
        "target_model_tasks": 3200, "resource_decision": "3200",
        "implementation_sha256": implementation_sha256(CudaModel),
        "formal_runner_sha256": hashlib.sha256(Path(formal_script.__file__).read_bytes()).hexdigest(),
        "models": {
            model: {"revision": revision, "slot": slot,
                    "format_adapter": "strict" if slot == 0 else "phi_json_fence_v1",
                    "gpu": "Tesla T4", "runtime": {"torch": "test-only"}}
            for slot, (model, revision) in enumerate(PINNED.items())
        },
        "preflight": {model: {"completed_model_tasks": 160, "gpu": "Tesla T4",
                              "runtime": {"torch": "test-only"}} for model in PINNED},
        "resource": {"available_ccu": 100, "projected_ccu": 20},
    }


def test_frozen_protocol_validation_requires_exact_matrix_and_reserve():
    protocol = _synthetic_protocol()
    streams, schedule = validate_frozen_protocol(protocol, next(iter(PINNED)))
    assert len(streams) == 40
    assert len(schedule) == 200
    protocol["status"] = "candidate"
    with pytest.raises(ValueError, match="frozen"):
        validate_frozen_protocol(protocol, next(iter(PINNED)))
    protocol["status"] = "frozen"
    protocol["resource"]["projected_ccu"] = 90
    with pytest.raises(ValueError, match="reserve"):
        validate_frozen_protocol(protocol, next(iter(PINNED)))


def test_frozen_protocol_detects_source_or_case_drift():
    protocol = _synthetic_protocol()
    protocol["stream_sha256"][0] = "0" * 64
    with pytest.raises(ValueError, match="stream manifest"):
        validate_frozen_protocol(protocol, next(iter(PINNED)))
    protocol = _synthetic_protocol()
    protocol["implementation_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Implementation changed"):
        validate_frozen_protocol(protocol, next(iter(PINNED)))
