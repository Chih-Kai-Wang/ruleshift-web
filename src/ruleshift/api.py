"""Local researcher workbench. Model observations are built separately by agents.py."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ruleshift.scoring import evaluate, reference_actions
from ruleshift.world import Action, RuleShiftEnv, replay

ROOT = Path(__file__).parents[2]
app = FastAPI(title="RuleShift researcher workbench", version="0.1.0")
sessions: dict[str, RuleShiftEnv] = {}
lock = threading.RLock()


class CreateWorld(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = Field(default=17, ge=0, le=1000000)
    schedule: Literal["stable", "single", "multi", "recurring"] = "recurring"


def get_world(session_id: str) -> RuleShiftEnv:
    if session_id not in sessions:
        raise HTTPException(404, "World session not found. Start a new world.")
    return sessions[session_id]


def researcher_view(env: RuleShiftEnv) -> dict:
    return {
        "mode": "researcher_not_agent_input",
        "observation": env.observation(),
        "world": env.snapshot()["state"],
        "events": env.snapshot()["events"],
        "score": evaluate(env.task_start, env.state) if env.state["done"] else None,
    }


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.1.0", "model_execution": "separate benchmark process"}


@app.post("/api/world")
def create_world(request: CreateWorld):
    with lock:
        if len(sessions) >= 100:
            sessions.pop(next(iter(sessions)))
        key = uuid.uuid4().hex
        env = RuleShiftEnv(request.schedule, "dev")
        env.reset(seed=request.seed)
        env.start_task()
        sessions[key] = env
        return {"session_id": key, **researcher_view(env)}


@app.get("/api/world/{session_id}")
def read_world(session_id: str):
    with lock:
        return researcher_view(get_world(session_id))


@app.post("/api/world/{session_id}/action")
def act(session_id: str, action: Action):
    with lock:
        env = get_world(session_id)
        try:
            env.step(action.model_dump())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return researcher_view(env)


@app.post("/api/world/{session_id}/next")
def next_task(session_id: str):
    with lock:
        env = get_world(session_id)
        try:
            env.start_task()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return researcher_view(env)


@app.post("/api/world/{session_id}/reference")
def reference(session_id: str):
    with lock:
        env = get_world(session_id)
        if env.state["done"]:
            raise HTTPException(409, "Task already closed")
        actions = reference_actions(env.task_start)
        # After a successful manual mutation only close; never apply it a second time.
        current_score = evaluate(
            env.task_start, {**env.state, "decision": {"decision": "complete", "reason": "ok"}}
        )
        if current_score["expected_decision"] == "complete" and current_score["state_ok"]:
            actions = [{"tool": "finish", "args": {"decision": "complete", "reason": "ok"}}]
        for action in actions:
            if not env.state["done"]:
                env.step(action)
        return {"execution_kind": "privileged_reference_not_llm", **researcher_view(env)}


@app.get("/api/world/{session_id}/replay")
def verify_replay(session_id: str):
    with lock:
        return replay(get_world(session_id).snapshot())


@app.get("/api/world/{session_id}/snapshot")
def download_snapshot(session_id: str):
    with lock:
        return get_world(session_id).snapshot()


@app.get("/api/experiments")
def experiments():
    rows = []
    for manifest_path in sorted((ROOT / "artifacts" / "runs").glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        root = manifest_path.parent
        count, status = 0, "initializing"
        if (root / "index.sqlite").exists():
            try:
                con = sqlite3.connect(f"file:{root / 'index.sqlite'}?mode=ro", uri=True)
                try:
                    initialized = con.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
                    ).fetchone()
                    if initialized:
                        count = con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                        status = "ready"
                finally:
                    con.close()
            except sqlite3.DatabaseError:
                count, status = None, "unavailable"
        rows.append(
            {
                "name": root.name,
                "completed": count,
                "planned": manifest["planned_tasks"],
                "split": manifest["config"]["split"],
                "model": manifest["config"]["model"],
                "available": status == "ready" and (root / "explorer.json").exists(),
                "status": status,
            }
        )
    return rows


@app.get("/api/experiments/{name}")
def experiment(name: str):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise HTTPException(400, "Invalid experiment name")
    path = ROOT / "artifacts" / "runs" / name / "explorer.json"
    if not path.exists():
        raise HTTPException(404, "Experiment export is not ready")
    return FileResponse(path)


@app.get("/{path:path}")
def frontend(path: str):
    dist = (ROOT / "web" / "dist").resolve()
    target = (dist / path).resolve()
    if not target.is_relative_to(dist):
        raise HTTPException(404, "Not found")
    if target.is_file():
        return FileResponse(target)
    if path.startswith("api/"):
        raise HTTPException(404, "API endpoint not found")
    if (dist / "index.html").exists():
        return FileResponse(dist / "index.html")
    raise HTTPException(503, "Build the web app with npm run build in web/ first")
