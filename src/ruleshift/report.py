"""Stream-level estimates, complete denominators and portable evidence exports."""

from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ruleshift.store import RunStore, atomic_json


def summarize(records: list, planned: int) -> dict:
    grouped = defaultdict(list)
    for r in records:
        grouped[r["policy"]].append(r)
    rows = []
    for policy, items in grouped.items():
        n = len(items)
        unchanged = [
            r
            for r in items
            if not any(
                e["kind"] == "start_task" and r["score"]["scope"] in e["changed_scopes"]
                for e in r["snapshot"]["events"]
            )
        ]
        rows.append(
            {
                "policy": policy,
                "n": n,
                "successes": sum(r["score"]["success"] for r in items),
                "success_rate": sum(r["score"]["success"] for r in items) / n,
                "unchanged_scope_n": len(unchanged),
                "unchanged_scope_successes": sum(r["score"]["success"] for r in unchanged),
                "stale_consistent_errors": sum(r["stale_consistent_error"] for r in items),
                **{
                    key: sum(r["cost"][key] for r in items)
                    for key in (
                        "tool_calls",
                        "policy_reads",
                        "illegal_attempts",
                        "prompt_tokens",
                        "completion_tokens",
                        "wall_seconds",
                        "model_seconds",
                    )
                },
            }
        )
    paired = []
    by_stream = defaultdict(lambda: defaultdict(list))
    for r in records:
        by_stream[(r["schedule"], r["seed"])][r["policy"]].append(r)
    for key, groups in by_stream.items():
        if "selective" in groups and "refresh" in groups:
            left, right = groups["selective"], groups["refresh"]
            if {r["task_index"] for r in left} == {r["task_index"] for r in right} and len(left) == 8:

                def rate(items):
                    return sum(r["score"]["success"] for r in items) / len(items)

                paired.append(
                    {"schedule": key[0], "seed": key[1], "success_difference": rate(left) - rate(right)}
                )
    comparison = None
    if paired:
        values = np.array([p["success_difference"] for p in paired])
        rng = np.random.default_rng(20260920)
        boot = rng.choice(values, size=(10000, len(values)), replace=True).mean(axis=1)
        comparison = {
            "contrast": "selective minus refresh",
            "unit": "paired task stream",
            "n_pairs": len(values),
            "mean_success_difference": float(values.mean()),
            "bootstrap_95_percent_interval": [float(x) for x in np.quantile(boot, [0.025, 0.975])],
            "pairs": paired,
        }
    recovery = []
    for key, groups in by_stream.items():
        for policy, items in groups.items():
            items = sorted(items, key=lambda r: r["task_index"])
            changes = {}
            for r in items:
                event = next(e for e in reversed(r["snapshot"]["events"]) if e["kind"] == "start_task")
                if event["changed_scopes"]:
                    changes[r["task_index"]] = event["changed_scopes"]
            for scope in ("returns", "fulfillment", "changes"):
                boundaries = sorted(at for at, scopes in changes.items() if scope in scopes)
                for position, at in enumerate(boundaries):
                    until = boundaries[position + 1] if position + 1 < len(boundaries) else 8
                    affected = [
                        r for r in items if at <= r["task_index"] < until and r["score"]["scope"] == scope
                    ]
                    first = next((i + 1 for i, r in enumerate(affected) if r["score"]["success"]), None)
                    recovery.append(
                        {
                            "schedule": key[0],
                            "seed": key[1],
                            "policy": policy,
                            "scope": scope,
                            "change_at": at,
                            "affected_tasks_observed": len(affected),
                            "tasks_to_first_success": first,
                            "censored": first is None,
                        }
                    )
    return {
        "completed_tasks": len(records),
        "planned_tasks": planned,
        "complete": len(records) == planned,
        "policies": rows,
        "paired_comparison": comparison,
        "recovery": recovery,
        "claims": "Frozen-weight, synthetic-retail, single-model pilot. Not a production or general-intelligence claim.",
    }


def compact_record(r: dict) -> dict:
    return {
        k: r[k]
        for k in (
            "stream",
            "schedule",
            "seed",
            "policy",
            "task_index",
            "score",
            "cost",
            "history",
            "memory_at_start",
            "memory_after",
            "stale_consistent_error",
        )
    } | {
        "order": r["snapshot"]["task_start"]["orders"][r["score"]["order_id"]],
        "rules": r["snapshot"]["task_start"]["rules"],
        "after": r["snapshot"]["state"]["orders"][r["score"]["order_id"]],
    }


def report(root: Path) -> dict:
    root = Path(root)
    store = RunStore(root)
    try:
        records = store.all()
    finally:
        store.close()
    manifest = json.loads((root / "manifest.json").read_text())
    summary = summarize(records, manifest["planned_tasks"])
    atomic_json(root / "summary.json", summary)
    if summary["policies"]:
        with (root / "summary.csv").open("w") as f:
            writer = csv.DictWriter(f, fieldnames=summary["policies"][0].keys())
            writer.writeheader()
            writer.writerows(summary["policies"])
    with gzip.open(root / "trajectories.jsonl.gz", "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (root / "metrics.jsonl").open("w") as f:
        for r in records:
            f.write(
                json.dumps(
                    {k: r[k] for k in ("stream", "schedule", "seed", "policy", "task_index", "score", "cost")}
                )
                + "\n"
            )
    atomic_json(
        root / "explorer.json",
        {"manifest": manifest, "summary": summary, "records": [compact_record(r) for r in records]},
    )
    lines = [
        "# Experiment report",
        "",
        f"Completed: **{len(records)} / {manifest['planned_tasks']}** tasks.",
        "",
        f"Model: `{manifest['config']['model']}`",
        "",
        "| Policy | Success | Tool calls | Policy reads | Total tokens |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary["policies"]:
        lines.append(
            f"| {row['policy']} | {row['successes']}/{row['n']} | {row['tool_calls']} | {row['policy_reads']} | {row['prompt_tokens'] + row['completion_tokens']} |"
        )
    if summary["paired_comparison"]:
        p = summary["paired_comparison"]
        low, high = p["bootstrap_95_percent_interval"]
        lines.extend(
            [
                "",
                f"Selective − refresh: {p['mean_success_difference']:.3f}; paired-stream bootstrap 95% CI [{low:.3f}, {high:.3f}], n={p['n_pairs']} streams.",
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation boundaries",
            "",
            summary["claims"],
            "All model failures remain in the denominator. Warmup evidence is shared; policy-managed reads are charged.",
            "The stale-evidence indicator is an observational consistency check, not a causal attribution.",
            "Full prompts, responses, world snapshots and replayable actions are in trajectories.jsonl.gz.",
        ]
    )
    (root / "REPORT.md").write_text("\n".join(lines) + "\n")
    return summary
