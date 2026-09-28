import copy
import json
import sqlite3

import pytest

from ruleshift.deterministic_controller import DeterministicController
from ruleshift.web_schedule import balanced_schedule
from ruleshift.web_stream_runner import parse_for_g3, run_stream, run_stream_checkpointed
from ruleshift.web_streams import make_split, make_stream
from scripts.audit_g3_streams import audit_row


def test_sequential_stream_keeps_memory_and_replays():
    spec = make_stream("development", "relevant_change", 0, 20260928)
    stale = run_stream(DeterministicController(), spec, "retrieval")
    checked = run_stream(DeterministicController(), spec, "source_dependent")
    assert len(stale["tasks"]) == len(checked["tasks"]) == 8
    assert stale["replay"]["verified"] and checked["replay"]["verified"]
    assert all(row["final_correct"] for row in stale["tasks"] + checked["tasks"])
    assert stale["tasks"][3]["server_rejections"] == 1
    assert checked["tasks"][3]["server_rejections"] == 0
    assert any(item["outcome"] == "reused_unchecked"
               for item in stale["tasks"][3]["memory_history"])
    assert stale["tasks"][4]["server_rejections"] == 0


def test_reversion_returns_original_validator_in_stream():
    spec = make_stream("development", "reversion", 1, 20260928)
    result = run_stream(DeterministicController(), spec, "source_dependent")
    assert all(row["final_correct"] for row in result["tasks"])
    assert result["tasks"][2]["expected_allowed"]
    assert not result["tasks"][3]["expected_allowed"]
    assert result["tasks"][6]["expected_allowed"]
    initial = next(event["response"]["revision"] for event in result["trace"]["events"]
                   if event["kind"] == "read" and event["request"]["scope"] == "returns")
    restored = next(event["response"]["revision"] for event in result["tasks"][6]["events"]
                    if event["kind"] == "read" and event["request"]["scope"] == "returns"
                    and event["status"] == 200)
    assert restored == initial


def test_stream_checkpoint_skips_completed_streams_and_rejects_mixing(tmp_path):
    class CountingController(DeterministicController):
        calls = 0

        def generate(self, system, user, max_new_tokens=96):
            self.calls += 1
            return super().generate(system, user, max_new_tokens)

    model = CountingController()
    streams = (make_stream("development", "unchanged", 0, 20260928),)
    strategies = ("retrieval",)
    first = run_stream_checkpointed(model, tmp_path, model.provenance, streams, strategies)
    assert first == {"planned": 1, "completed": 1, "complete": True}
    assert model.calls == 8
    assert run_stream_checkpointed(model, tmp_path, model.provenance, streams, strategies) == first
    assert model.calls == 8
    with pytest.raises(ValueError, match="different implementation or matrix"):
        run_stream_checkpointed(model, tmp_path, {"revision": "different"}, streams, strategies)


def test_v1_selective_refreshes_after_policy_block_only():
    class AlwaysAttempt:
        def generate(self, system, user, max_new_tokens=96):
            return {"text": '{"attempt":true,"reason":"ok"}',
                    "prompt_tokens": 1, "completion_tokens": 1, "seconds": 0.0}

    spec = make_stream("development", "relevant_change", 0, 20260928)
    retrieval = run_stream(AlwaysAttempt(), spec, "retrieval")
    selective = run_stream(AlwaysAttempt(), spec, "v1_selective")
    assert len(retrieval["tasks"][4]["responses"]) == 1
    assert len(selective["tasks"][4]["responses"]) == 2
    assert len(selective["tasks"][4]["attempts"]) == 2
    assert any(item["outcome"] == "validated_304"
               for item in selective["tasks"][4]["memory_history"])


def test_phi_fence_adapter_preserves_semantic_validation():
    valid = '```json\n\n{"attempt":false,"reason":"discount_ineligible"}\n\n```'
    contradictory = '```json\n\n{"attempt":true,"reason":"discount_ineligible"}\n\n```'
    assert parse_for_g3(valid) is None
    assert parse_for_g3(valid, "phi_json_fence_v1") == {
        "attempt": False, "reason": "discount_ineligible",
    }
    assert parse_for_g3(contradictory, "phi_json_fence_v1") is None
    assert parse_for_g3('intro\n' + valid, "phi_json_fence_v1") is None


def test_checkpoint_records_explicit_balanced_schedule(tmp_path):
    import json

    streams = make_split("development", 20260928, 2)
    strategies = ("retrieval", "source_dependent")
    schedule = balanced_schedule(streams, strategies, 20261001, 0)
    model = DeterministicController()
    result = run_stream_checkpointed(model, tmp_path, model.provenance,
                                     streams, strategies, schedule=schedule)
    assert result == {"planned": 16, "completed": 16, "complete": True}
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert [tuple(item) for item in manifest["schedule"]] == list(schedule)
    assert run_stream_checkpointed(model, tmp_path, model.provenance,
                                   streams, strategies, schedule=schedule) == result
    with pytest.raises(ValueError, match="Schedule must include"):
        run_stream_checkpointed(model, tmp_path / "bad", model.provenance,
                                streams, strategies, schedule=schedule[:-1])


def test_formal_audit_checks_agent_prompt_and_evidence_provenance():
    spec = make_stream("development", "relevant_change", 0, 20260928)
    row = run_stream(DeterministicController(), spec, "source_dependent")
    assert audit_row(row, require_provenance=True)["correct"] == 8

    changed = copy.deepcopy(row)
    changed["tasks"][0]["responses"][0]["agent_input"] = '{}'
    with pytest.raises(ValueError, match="Prompt provenance mismatch"):
        audit_row(changed, require_provenance=True)

    changed = copy.deepcopy(row)
    changed["tasks"][0]["evidence_views"][0][0]["revision"] = "future"
    with pytest.raises(ValueError, match="Prompt provenance mismatch|Future or invented evidence"):
        audit_row(changed, require_provenance=True)


def test_checkpoint_preserves_fatal_model_failure_and_stops_resume(tmp_path):
    class FailingModel:
        def __init__(self):
            self.provenance = {"model": "test-failure"}

        def generate(self, system, user, max_new_tokens=96):
            raise RuntimeError("model unavailable")

    model = FailingModel()
    streams = (make_stream("development", "unchanged", 0, 20260928),)
    with pytest.raises(RuntimeError, match="model unavailable"):
        run_stream_checkpointed(model, tmp_path, model.provenance, streams, ("retrieval",))
    with sqlite3.connect(tmp_path / "results.sqlite") as con:
        failures = [json.loads(payload) for (payload,) in con.execute("SELECT payload FROM failures")]
        assert con.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0
    assert len(failures) == 1
    assert failures[0]["exception_type"] == "RuntimeError"
    with pytest.raises(RuntimeError, match="recorded failures"):
        run_stream_checkpointed(model, tmp_path, model.provenance, streams, ("retrieval",))
