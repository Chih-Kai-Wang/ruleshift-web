import sqlite3
import sys

import pytest

from ruleshift.deterministic_controller import DeterministicController
from ruleshift.web_stream_runner import run_stream_checkpointed
from ruleshift.web_streams import SCENARIOS, make_stream
from scripts.audit_g3_streams import _paired_interval, main


def test_paired_stream_interval_uses_streams_not_individual_tasks():
    rows = []
    for scenario in SCENARIOS:
        for index in range(10):
            stream_id = f"tes-{scenario}-{index:02d}"
            rows.extend((
                {"stream_id": stream_id, "scenario": scenario,
                 "strategy": "retrieval", "correct": 5, "agent_http_requests": 8},
                {"stream_id": stream_id, "scenario": scenario,
                 "strategy": "source_dependent", "correct": 6,
                 "agent_http_requests": 16},
            ))
    result = _paired_interval(rows, "retrieval")
    assert result["streams"] == 40
    assert result["mean_accuracy_difference"] == 0.125
    assert result["ci95"] == [0.125, 0.125]
    requests = _paired_interval(rows, "retrieval", "agent_http_requests",
                                "http_requests_per_task")
    assert requests["mean_http_requests_per_task_difference"] == 1
    assert requests["ci95"] == [1, 1]


def test_checkpoint_audit_rejects_key_payload_mismatch(tmp_path, monkeypatch, capsys):
    model = DeterministicController()
    stream = make_stream("development", "unchanged", 0, 20260928)
    run_stream_checkpointed(model, tmp_path, model.provenance, (stream,), ("retrieval",))
    monkeypatch.setattr(sys, "argv", ["audit_g3_streams.py", str(tmp_path)])
    main()
    assert '"streams_audited": 1' in capsys.readouterr().out
    with sqlite3.connect(tmp_path / "results.sqlite") as db:
        db.execute("UPDATE results SET case_key = ?", ('["altered","sha","retrieval"]',))
    with pytest.raises(ValueError, match="Checkpoint key"):
        main()
