import json

import pytest

from ruleshift.audit import audit
from ruleshift.experiment import run_experiment
from ruleshift.store import RunStore


class StubModel:
    """Execution fixture only, deliberately not a performance baseline."""

    def __init__(self, fail_at=None):
        self.calls = 0
        self.fail_at = fail_at

    def tokens(self, text):
        return len(text)

    def generate(self, user):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError("simulated interruption")
        text = '{"tool":"finish","args":{"decision":"deny","reason":"too_old"}}'
        return {
            "text": text,
            "prompt": user,
            "prompt_tokens": len(user),
            "completion_tokens": len(text),
            "seconds": 0.0,
        }


def test_resume_preserves_completed_rows_and_rejects_changed_config(tmp_path):
    broken = StubModel(fail_at=4)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_experiment(tmp_path, smoke=True, model=broken)
    store = RunStore(tmp_path)
    before = store.all()
    store.close()
    assert len(before) == 3
    resumed = StubModel()
    run_experiment(tmp_path, smoke=True, model=resumed)
    assert resumed.calls == 13
    store = RunStore(tmp_path)
    after = store.all()
    store.close()
    by_key = {(r["stream"], r["task_index"]): r for r in after}
    for row in before:
        assert by_key[row["stream"], row["task_index"]] == row
    never_called = StubModel()
    run_experiment(tmp_path, smoke=True, model=never_called)
    assert never_called.calls == 0
    with pytest.raises(RuntimeError, match="configuration"):
        run_experiment(tmp_path, smoke=True, split="validation", model=never_called)
    assert audit(tmp_path)["records"] == 16


def test_audit_rejects_missing_matrix_and_tampered_source(tmp_path):
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_experiment(tmp_path, smoke=True, model=StubModel(fail_at=2))
    assert audit(tmp_path, require_complete=False)["missing"] == 15
    with pytest.raises(ValueError, match="Incomplete matrix"):
        audit(tmp_path)
    source = tmp_path / "source" / "agents.py"
    source.write_text(source.read_text() + "\n# changed\n")
    with pytest.raises(ValueError, match="Archived execution source"):
        audit(tmp_path, require_complete=False)


def test_canonical_export_recovers_missing_individual_export(tmp_path):
    from ruleshift.report import report

    run_experiment(tmp_path, smoke=True, model=StubModel())
    target = next(tmp_path.glob("*/task-00.json"))
    target.unlink()
    summary = report(tmp_path)
    assert summary["complete"] and summary["completed_tasks"] == 16
    assert len(json.loads((tmp_path / "explorer.json").read_text())["records"]) == 16


def test_portable_export_audit_and_tamper_detection(tmp_path):
    import gzip
    import shutil

    from ruleshift.report import report

    run = tmp_path / "run"
    run_experiment(run, smoke=True, model=StubModel())
    report(run)
    exported = tmp_path / "release"
    exported.mkdir()
    for name in ("manifest.json", "trajectories.jsonl.gz"):
        shutil.copyfile(run / name, exported / name)
    shutil.copytree(run / "source", exported / "source")
    assert audit(exported)["records"] == 16
    assert audit(run, exported=True)["records"] == 16
    with gzip.open(exported / "trajectories.jsonl.gz", "rt") as f:
        rows = [json.loads(line) for line in f]
    rows[0]["cost"]["prompt_tokens"] += 1
    with gzip.open(exported / "trajectories.jsonl.gz", "wt") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="Incorrect prompt_tokens"):
        audit(exported)
    assert not (exported / "index.sqlite").exists()


def test_export_audit_rejects_misreported_summary(tmp_path):
    from ruleshift.report import report

    run_experiment(tmp_path, smoke=True, model=StubModel())
    report(tmp_path)
    summary_path = tmp_path / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["policies"][0]["successes"] += 1
    summary_path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="Published summary"):
        audit(tmp_path, exported=True)


@pytest.mark.parametrize("field", ["prompt", "memory_after", "model_seconds"])
def test_export_audit_rejects_prompt_memory_and_time_tampering(tmp_path, field):
    import gzip

    from ruleshift.report import report

    run_experiment(tmp_path, smoke=True, model=StubModel())
    report(tmp_path)
    path = tmp_path / "trajectories.jsonl.gz"
    with gzip.open(path, "rt") as f:
        rows = [json.loads(line) for line in f]
    if field == "prompt":
        rows[0]["responses"][0]["prompt"] += " hidden answer"
    elif field == "memory_after":
        rows[0]["memory_after"]["returns"]["policy"]["window_days"] = 999
    else:
        rows[0]["cost"]["model_seconds"] += 1
    with gzip.open(path, "wt") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="prompt|memory|time"):
        audit(tmp_path, exported=True)
