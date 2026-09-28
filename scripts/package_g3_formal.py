"""Package the exact frozen G3 protocol and source after the preflight gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from ruleshift.cuda_model import CudaModel
from ruleshift.deterministic_controller import DeterministicController
from ruleshift.web_stream_runner import implementation_sha256
from scripts.run_g3_colab_formal import PINNED, validate_frozen_protocol

ROOT = Path(__file__).parents[1]
FILES = (
    "src/ruleshift/web_lab.py",
    "src/ruleshift/web_memory.py",
    "src/ruleshift/web_batch.py",
    "src/ruleshift/web_streams.py",
    "src/ruleshift/web_schedule.py",
    "src/ruleshift/web_stream_runner.py",
    "src/ruleshift/cuda_model.py",
    "src/ruleshift/deterministic_controller.py",
    "scripts/run_g3_colab_formal.py",
    "scripts/run_g3_deterministic_baseline.py",
    "scripts/audit_g3_streams.py",
    "research/www2027/COLAB_G3_FORMAL.md",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    args = parser.parse_args()
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    for model_id in PINNED:
        validate_frozen_protocol(protocol, model_id)
    if protocol["implementation_sha256"] != implementation_sha256(CudaModel):
        raise ValueError("Frozen implementation no longer matches source")
    if (protocol.get("control", {}).get("implementation_sha256") !=
            implementation_sha256(DeterministicController)):
        raise ValueError("Frozen no-LLM control no longer matches source")
    audit_path = ROOT / "scripts/audit_g3_streams.py"
    if protocol.get("audit_script_sha256") != hashlib.sha256(audit_path.read_bytes()).hexdigest():
        raise ValueError("Audit script changed after freeze")
    output = ROOT / "research/www2027/ruleshift-web-g3-formal.zip"
    if output.exists():
        raise FileExistsError("Formal package already exists; do not overwrite it")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("src/ruleshift/__init__.py", '"""Frozen RuleShift-Web v2 package."""\n')
        for name in FILES:
            archive.write(ROOT / name, name)
        archive.writestr("research/www2027/G3_FROZEN_PROTOCOL.json", protocol_bytes)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.parent / (output.name + ".sha256")).write_text(f"{digest}  {output.name}\n")
    print(json.dumps({"output": str(output), "sha256": digest,
                      "size_bytes": output.stat().st_size}, sort_keys=True))


if __name__ == "__main__":
    main()
