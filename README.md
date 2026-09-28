# RuleShift-Web

**A replayable workbench for auditing agent memory under changing Web policies.**

This public research snapshot contains the local HTTP policy site, memory
strategies, transaction guard, interactive replay interface, frozen protocol,
formal results, raw SQLite checkpoints, independent audit code, and a working
Demo manuscript. The manuscript is a **pre-submission draft**, not a peer-reviewed
or accepted WWW 2027 paper. Author: **Chih-Kai Wang**, National Taipei University
of Education.

RuleShift-Web makes three distinct states visible: the policy representation
held by an agent, the current HTTP representation, and the rule enforced when a
transaction commits. The site can publish a new rule, return `304` for an
unchanged representation, and reject a stale transaction with `409` without
changing order state. Offline traces remain inspectable without network access.

## Evidence and scope

The frozen study contains **3,200 model-task executions** across two pinned
small models and five evidence strategies, plus **1,600 no-LLM control
decisions**. Each strategy is evaluated on paired eight-task streams. The
original model/control checkpoints are included under
`research/www2027/g3-formal-*-20260928/`; the protocol and independently
recomputed results are in
[`G3_FROZEN_PROTOCOL.json`](research/www2027/G3_FROZEN_PROTOCOL.json) and
[`G3_FORMAL_RESULTS.md`](research/www2027/G3_FORMAL_RESULTS.md).

Source-dependent validation matched all-source conditional validation on this
one-relevant-source harness while issuing four fewer policy reads per task.
Always-refresh had higher observed accuracy for both models, and the no-LLM
controller was stronger than either model on this controlled task. The result
supports an **inspectable research instrument**, not a generally superior
memory policy or reliability claim for real commerce websites.

## Run the local demonstration

Use Python 3.12 or 3.13 and [`uv`](https://docs.astral.sh/uv/):

```sh
uv sync --frozen --extra dev
uv run uvicorn ruleshift.web_lab:create_app --factory --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765/lab>. Follow
[`G4_DEMO_SCRIPT.md`](research/www2027/G4_DEMO_SCRIPT.md) to read a policy,
publish a change, attempt a transaction, and inspect the saved event trace.
Open `research/www2027/web_lab_ui.html` directly for the offline fallback.
The local service has no authentication; keep it bound to loopback.

## Independently recompute the saved results

```sh
PYTHONPATH=. uv run pytest -q
uv run python scripts/audit_g3_streams.py research/www2027/g3-formal-qwen-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json
uv run python scripts/audit_g3_streams.py research/www2027/g3-formal-phi-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json
uv run python scripts/audit_g3_streams.py research/www2027/g3-formal-control-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json
```

See [`G4_REPRODUCIBILITY.md`](research/www2027/G4_REPRODUCIBILITY.md) for
expected counts, hashes, model revisions, and the Safari trace replay.
[`COLAB_G3_FORMAL.md`](research/www2027/COLAB_G3_FORMAL.md) records the
historical CUDA runtime. Model weights and credentials are not bundled.
Re-running the frozen held-out matrix after changing code or prompts does not
reproduce the reported experiment.

## Manuscript and release boundaries

The current [three-page manuscript](research/www2027/paper/ruleshift_web_demo.pdf)
and [LaTeX source](research/www2027/paper/ruleshift_web_demo.tex) are working
versions. They disclose generative-AI assistance and report adverse as well as
positive findings. A human final scientific review, funding decision, and
formal conference submission are still outstanding. This GitHub release does
not imply arXiv posting or conference acceptance.

Code is Apache-2.0; authored synthetic task data and released experiment
records are CC BY 4.0, subject to third-party rights. See
[`DATA_LICENSE.md`](DATA_LICENSE.md) and [`THIRD_PARTY.md`](THIRD_PARTY.md).
The system builds on the earlier
[`RuleShift`](https://github.com/f0909172434/ruleshift) pilot; the older pilot's
results are not part of the frozen Web study.
