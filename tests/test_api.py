from fastapi.testclient import TestClient

from ruleshift.api import app

client = TestClient(app)


def test_workbench_full_stream_and_replay():
    r = client.post("/api/world", json={"seed": 17, "schedule": "recurring"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert r.json()["mode"] == "researcher_not_agent_input"
    assert client.post(f"/api/world/{sid}/next").status_code == 409
    for i in range(8):
        done = client.post(f"/api/world/{sid}/reference")
        assert done.json()["score"]["success"]
        assert done.json()["execution_kind"] == "privileged_reference_not_llm"
        if i < 7:
            assert client.post(f"/api/world/{sid}/next").status_code == 200
    assert client.post(f"/api/world/{sid}/next").status_code == 409
    assert client.get(f"/api/world/{sid}/replay").json()["verified"]


def test_schema_and_unknown_sessions():
    assert client.post("/api/world", json={"schedule": "anything"}).status_code == 422
    assert client.get("/api/world/unknown").status_code == 404
    assert client.get("/api/not-a-route").status_code == 404
    assert client.post("/api/world", json={"seed": -1}).status_code == 422


def test_experiment_listing_handles_initializing_and_corrupt_indexes(tmp_path, monkeypatch):
    import json
    import sqlite3

    from ruleshift import api

    monkeypatch.setattr(api, "ROOT", tmp_path)
    for name in ("initializing", "broken", "ready"):
        run = tmp_path / "artifacts" / "runs" / name
        run.mkdir(parents=True)
        (run / "manifest.json").write_text(
            json.dumps({"planned_tasks": 800, "config": {"split": "test", "model": "fixture"}})
        )
        (run / "explorer.json").write_text("{}")
        if name == "broken":
            (run / "index.sqlite").write_bytes(b"not a database")
        else:
            with sqlite3.connect(run / "index.sqlite") as con:
                if name == "ready":
                    con.execute("CREATE TABLE tasks (payload TEXT)")
                    con.execute("INSERT INTO tasks VALUES ('{}')")
    response = client.get("/api/experiments")
    assert response.status_code == 200
    rows = {r["name"]: r for r in response.json()}
    assert rows["initializing"]["completed"] == 0
    assert rows["initializing"]["status"] == "initializing"
    assert rows["broken"]["completed"] is None
    assert rows["broken"]["status"] == "unavailable"
    assert not rows["initializing"]["available"] and not rows["broken"]["available"]
    assert rows["ready"]["completed"] == 1 and rows["ready"]["available"]
