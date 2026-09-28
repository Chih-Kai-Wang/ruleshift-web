import pytest

from scripts.freeze_g3_protocol import resource_decision


def test_resource_gate_selects_predeclared_scale_before_test():
    base = {"qwen_total_wall_seconds": 600, "phi_total_wall_seconds": 600,
            "qwen_total_load_seconds": 100, "phi_total_load_seconds": 100}
    full, full_record = resource_decision({**base, "ccu_before": 190, "ccu_after": 189})
    assert full == 10
    assert full_record["projected_ccu"] <= full_record["available_ccu"] * 0.8
    reduced, reduced_record = resource_decision({**base, "ccu_before": 20, "ccu_after": 19})
    assert reduced == 5
    assert reduced_record["projected_ccu"] <= reduced_record["available_ccu"] * 0.8


def test_resource_gate_handles_rounded_ccu_display_and_insufficient_balance():
    base = {"qwen_total_wall_seconds": 600, "phi_total_wall_seconds": 600,
            "qwen_total_load_seconds": 100, "phi_total_load_seconds": 100}
    scale, record = resource_decision({**base, "ccu_before": 20, "ccu_after": 20})
    assert scale == 10
    assert record["ccu_debit_resolution"] == "below_display_resolution"
    assert record["rate_used_ccu_per_hour"] == 1.15
    with pytest.raises(ValueError, match="nonincreasing"):
        resource_decision({**base, "ccu_before": 20, "ccu_after": 21})
    with pytest.raises(ValueError, match="nonincreasing"):
        resource_decision({**base, "ccu_before": float("nan"), "ccu_after": 20})
    with pytest.raises(ValueError, match="Neither predeclared"):
        resource_decision({**base, "ccu_before": 2, "ccu_after": 1})
