import hashlib
import runpy
from pathlib import Path


def test_compact_checksums_cover_only_local_files(tmp_path):
    helper = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "package_evidence.py"))[
        "write_checksums"
    ]
    (tmp_path / "summary.json").write_text('{"complete":true}')
    (tmp_path / "README.md").write_text("Compact evidence only")
    (tmp_path / "SHA256SUMS").write_text("stale  absent-file\n")
    helper(tmp_path)
    lines = (tmp_path / "SHA256SUMS").read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        digest, filename = line.split("  ", 1)
        assert hashlib.sha256((tmp_path / filename).read_bytes()).hexdigest() == digest
