# G3 frozen held-out Colab run — use only after protocol freeze

The formal package is built **only after** both development preflights are
audited and `G3_FROZEN_PROTOCOL.json` is created by
`scripts/freeze_g3_protocol.py`. A code-only candidate or the development
preflight package is not a formal result. Check the package `.sha256` before
extracting it. The frozen file fixes the source, model revisions, response
adapters, stream split, strategy schedule, resource scale, and analysis.

In a user-controlled Colab GPU runtime, use a durable checkpoint location
or download a complete checkpoint archive after each model run. The
2026-09-28 L4 execution used `/content/RuleShift-Web/G3-formal-{qwen,phi}`
and downloaded each zip to the local project; Drive was not mounted for G3.
Record the CCU balance before and after each model run. Keep the original
terminal JSON, `manifest.json`, and `results.sqlite` for both models. If a
runtime disconnects, rerun the same command with the **same** package and
checkpoint directory; each complete eight-task stream/strategy arm is
committed once. A failed arm is recorded in SQLite and stops automatic resume
until it is investigated; do not delete failed rows or silently rerun them.
Do not change the protocol or code while resuming.

```python
import hashlib, pathlib, zipfile
archive = pathlib.Path('/content/ruleshift-web-g3-formal.zip')
expected = pathlib.Path('/content/ruleshift-web-g3-formal.zip.sha256').read_text().split()[0]
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
with zipfile.ZipFile(archive) as source:
    source.extractall('/content/ruleshift-web-g3-formal')
%pip install 'transformers==4.57.1' 'accelerate==1.11.0' 'huggingface-hub==0.36.0' 'fastapi>=0.115,<1' 'httpx>=0.28,<1' 'pydantic>=2.10,<3'
# Optional: mount Drive only if the user approves the notebook's Drive access.
```

```python
!cd /content/ruleshift-web-g3-formal && PYTHONPATH=.:src python scripts/run_g3_colab_formal.py --model Qwen/Qwen3-4B-Instruct-2507 --protocol research/www2027/G3_FROZEN_PROTOCOL.json --output /content/RuleShift-Web/G3-formal-qwen
!cd /content/ruleshift-web-g3-formal && PYTHONPATH=.:src python scripts/run_g3_colab_formal.py --model microsoft/Phi-4-mini-instruct --protocol research/www2027/G3_FROZEN_PROTOCOL.json --output /content/RuleShift-Web/G3-formal-phi
```

Run `scripts/audit_g3_streams.py` separately against each transferred
checkpoint with `--protocol G3_FROZEN_PROTOCOL.json`. The audit verifies raw
origin events and recomputes outcomes and paired intervals. No paper claim is
made until both models' complete checkpoints and the resource record pass
independent review. A single-model or partial run remains incomplete evidence.
The same frozen package also contains
`scripts/run_g3_deterministic_baseline.py`; run it once on a local CPU with
the frozen protocol and its own checkpoint directory, then audit it with the
same audit command. This no-LLM control is reported separately from the 3,200
model tasks.
