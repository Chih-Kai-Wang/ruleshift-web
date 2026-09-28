"""Atomic run artifacts and SQLite checkpoint index. No model keys are stored."""

import json
import os
import sqlite3
from pathlib import Path


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)


class RunStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "index.sqlite")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS tasks (stream TEXT, task_index INTEGER, payload TEXT NOT NULL, PRIMARY KEY(stream,task_index))"
        )
        self.db.commit()

    def save(self, stream: str, task_index: int, payload: dict) -> None:
        # SQLite is canonical. A crash between SQLite and export is repaired on resume.
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO tasks VALUES (?,?,?)", (stream, task_index, json.dumps(payload))
            )
        atomic_json(self.root / stream / f"task-{task_index:02d}.json", payload)

    def latest(self, stream: str) -> dict | None:
        row = self.db.execute(
            "SELECT payload FROM tasks WHERE stream=? ORDER BY task_index DESC LIMIT 1", (stream,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def all(self) -> list[dict]:
        return [
            json.loads(r[0]) for r in self.db.execute("SELECT payload FROM tasks ORDER BY stream,task_index")
        ]

    def close(self):
        self.db.close()
