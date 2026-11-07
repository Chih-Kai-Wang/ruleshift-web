# RuleShift-Web

RuleShift-Web is a local research workbench for studying what happens when a website changes its policy while an agent is still holding the old one. You can publish a rule change, watch an agent act on cached evidence, and replay every HTTP event afterward.

The workbench keeps three things visible and separate: the policy the agent holds, the policy the site currently serves, and the rule the site enforces when a transaction commits. The site can publish a new rule, answer `304` when a representation has not changed, and reject a stale transaction with `409` without touching order state. Saved traces can be inspected offline.

This public research snapshot contains the local HTTP policy site, memory strategies, transaction guard, replay interface, frozen protocol, formal results, raw SQLite checkpoints, independent audit code, and a working Demo manuscript. The manuscript is a pre-submission draft. It has not been peer reviewed or accepted at WWW 2027. The author is Chih-Kai Wang, National Taipei University of Education.

## Evidence and scope

The frozen study ran **3,200 model-task executions**: two pinned small models, five evidence strategies, paired eight-task streams. A separate no-LLM controller made **1,600 control decisions** on the same streams. The original model and control checkpoints are under `research/www2027/g3-formal-*-20260928/`. The protocol is in [`G3_FROZEN_PROTOCOL.json`](research/www2027/G3_FROZEN_PROTOCOL.json), and the independently recomputed results are in [`G3_FORMAL_RESULTS.md`](research/www2027/G3_FORMAL_RESULTS.md).

Source-dependent validation, the proposed strategy, matched all-source conditional validation in accuracy while issuing four fewer policy reads per task. That saving follows from this harness having one relevant source. Always-refresh had higher observed accuracy than source-dependent validation for both models. The no-LLM controller was stronger than either model on this controlled task. The results support the workbench as a research instrument. They do not show a generally better memory policy, and they say nothing about reliability on real commerce websites.

## Run the local demonstration

Use Python 3.12 or 3.13 and [`uv`](https://docs.astral.sh/uv/):

```sh
uv sync --frozen --extra dev
uv run uvicorn ruleshift.web_lab:create_app --factory --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765/lab>. The walkthrough in
[`G4_DEMO_SCRIPT.md`](research/www2027/G4_DEMO_SCRIPT.md) reads a policy,
publishes a change, attempts a transaction, and inspects the saved event trace.
For the offline fallback, open `research/www2027/web_lab_ui.html` directly.
The local service has no authentication, so keep it bound to loopback.

## Independently recompute the saved results

```sh
PYTHONPATH=. uv run pytest -q
uv run python scripts/audit_g3_streams.py research/www2027/g3-formal-qwen-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json
uv run python scripts/audit_g3_streams.py research/www2027/g3-formal-phi-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json
uv run python scripts/audit_g3_streams.py research/www2027/g3-formal-control-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json
```

[`G4_REPRODUCIBILITY.md`](research/www2027/G4_REPRODUCIBILITY.md) lists the
expected counts, hashes, model revisions, and the Safari trace replay.
[`COLAB_G3_FORMAL.md`](research/www2027/COLAB_G3_FORMAL.md) records the
historical CUDA runtime. Model weights and credentials are not bundled.
If you change code or prompts and re-run the frozen held-out matrix, you are
running a new experiment, not reproducing the reported one.

## Manuscript and release boundaries

The [three-page manuscript](research/www2027/paper/ruleshift_web_demo.pdf)
and its [LaTeX source](research/www2027/paper/ruleshift_web_demo.tex) are working
versions. They disclose generative-AI assistance and report the adverse
findings alongside the positive ones. A final human scientific review, a funding
decision, and formal conference submission are still outstanding. This GitHub
release has not been posted to arXiv or accepted by any conference.

Code is licensed under Apache-2.0. Authored synthetic task data and released
experiment records are licensed under CC BY 4.0, subject to third-party rights. See
[`DATA_LICENSE.md`](DATA_LICENSE.md) and [`THIRD_PARTY.md`](THIRD_PARTY.md).
The system builds on the earlier
[`RuleShift`](https://github.com/f0909172434/ruleshift) pilot. That pilot's
results are not part of the frozen Web study.
