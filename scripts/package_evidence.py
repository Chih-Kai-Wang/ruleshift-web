"""Package a completed, audited run using an explicit public-file allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

from ruleshift.audit import audit


def write_checksums(directory: Path):
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (directory / "SHA256SUMS").write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run = args.run.resolve()
    result = audit(run, exported=True)
    if not result["complete"]:
        raise SystemExit("Refusing to package an incomplete experiment")
    summary = json.loads((run / "summary.json").read_text())
    if not summary["complete"] or summary["completed_tasks"] != result["records"]:
        raise SystemExit("Summary does not match audited matrix")
    destination = root / "artifacts" / "release" / "ruleshift-test-v1"
    if destination.exists():
        raise SystemExit("Release staging already exists; choose a fresh version")
    destination.mkdir(parents=True)
    for name in [
        "manifest.json",
        "summary.json",
        "summary.csv",
        "metrics.jsonl",
        "REPORT.md",
        "trajectories.jsonl.gz",
    ]:
        shutil.copyfile(run / name, destination / name)
    shutil.copytree(run / "source", destination / "source")
    for name in ["LICENSE", "DATA_LICENSE.md", "THIRD_PARTY.md"]:
        shutil.copyfile(root / name, destination / name)
    (destination / "third_party").mkdir()
    shutil.copyfile(root / "third_party" / "CC-BY-4.0.txt", destination / "third_party" / "CC-BY-4.0.txt")
    (destination / "integrity.json").write_text(json.dumps(result, indent=2) + "\n")
    (destination / "README.md").write_text("""# RuleShift frozen test evidence

800 measured tasks. All failures retained. See REPORT.md and summary.json.
The source/ directory is the exact archived execution implementation, protocol and lock.

From the corresponding RuleShift release checkout, after installing its dependencies:

    uv run python -m ruleshift.audit /path/to/ruleshift-test-v1 --exported

This recomputes world replay, scores, matrix membership and recorded accounting.
It does not rerun neural inference or independently retokenize archived responses.
Validate file integrity with `shasum -a 256 -c SHA256SUMS` inside this directory.
Shared setup observations cost three policy reads per world and are excluded from
reported in-run query totals; all strategy-managed in-run reads are charged.
The static site provides a compact replay; the gzip file contains full prompts,
responses and snapshots. No model weights or credentials are included.
""")
    audit(destination, exported=True)
    files = sorted(p for p in destination.rglob("*") if p.is_file())
    checksums = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(destination).as_posix()}\n"
        for p in files
    )
    (destination / "SHA256SUMS").write_text(checksums)
    archive = destination.with_suffix(".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                info = tar.gettarinfo(
                    path, arcname=str(Path(destination.name) / path.relative_to(destination))
                )
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with path.open("rb") as f:
                    tar.addfile(info, f)
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n"
    )
    evidence = root / "evidence" / "test-v1"
    evidence.mkdir(parents=True, exist_ok=True)
    for name in [
        "manifest.json",
        "summary.json",
        "summary.csv",
        "metrics.jsonl",
        "REPORT.md",
        "integrity.json",
    ]:
        shutil.copyfile(destination / name, evidence / name)
    shutil.copyfile(archive.with_suffix(archive.suffix + ".sha256"), evidence / "archive.sha256")
    write_checksums(evidence)
    public = root / "web" / "public"
    public.mkdir(exist_ok=True)
    shutil.copyfile(run / "explorer.json", public / "explorer.json")
    print(
        json.dumps(
            {"archive": str(archive), "bytes": archive.stat().st_size, "verified_records": result["records"]}
        )
    )


if __name__ == "__main__":
    main()
