# Reproducing the RuleShift-Web Demo evidence

The formal results are frozen held-out evidence. Do not rerun the test set
with changed prompts, model revisions, parsers, or stream definitions and
combine it with this matrix.

The protocol is G3_FROZEN_PROTOCOL.json, SHA-256
3ef328fbdbb02ff2862445751f8a4f261a2e15014253f81cde72a4a8980f34d8.
The CUDA package is ruleshift-web-g3-formal.zip, SHA-256
6d0375e27d1e2f7e3e21405b494c3c6a5ce4f6bdb5b90bd14ce8c74c462bbfbb.
The transferred Qwen and Phi checkpoint zips have SHA-256 values
996254968d207c739648e3a8ad22fead891e6e99db26ac45c9cc017da0d9f9f1
and 61f23d738b6df7d43ef167269ae5bce45a2b66332466cb8c119ac98adb8e84ed.
Each model directory contains manifest.json, results.sqlite, and
formal_summary.json. The deterministic control has its own checkpoint.
Development MLX, T4, and L4 pilots remain separate.

From the repository root, independently recompute each checkpoint:

    PYTHONPATH=.:src .venv/bin/python scripts/audit_g3_streams.py research/www2027/g3-formal-qwen-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json
    PYTHONPATH=.:src .venv/bin/python scripts/audit_g3_streams.py research/www2027/g3-formal-phi-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json
    PYTHONPATH=.:src .venv/bin/python scripts/audit_g3_streams.py research/www2027/g3-formal-control-20260928 --protocol research/www2027/G3_FROZEN_PROTOCOL.json

Saved independent outputs are G3_FORMAL_QWEN_AUDIT.json,
G3_FORMAL_PHI_AUDIT.json, and G3_FORMAL_CONTROL_AUDIT.json. The auditor
checks stream identity, frozen order, model provenance, public prompt
content, response format, decisions, HTTP events, state changes, replay,
request and token totals, and scenario-stratified paired intervals.
Each model must have 200 complete arms and 1,600 tasks; the control is
200 arms and 1,600 decisions. A fatal failure is never silently counted
as complete.

The formal models are Qwen3-4B-Instruct-2507 revision
cdbee75f17c01a7cc42f958dc650907174af0554 and Phi-4-mini-instruct
revision cfbefacb99257ffa30c83adab238a50856ac3083. Both used
greedy float16 inference on NVIDIA L4 without CPU or disk offload.
Phi alone used the predeclared exact Markdown-fence adapter. Runtime
versions are in the frozen protocol and manifests. The two model scripts
ran for 930.53 and 993.06 seconds, excluding environment setup. Colab
CCU billing is account-shared and UI-rounded; see
G3_FORMAL_RESOURCE_OBSERVATION.json.

For the local HTTP demonstration, follow G4_DEMO_SCRIPT.md. To
independently replay the Safari trace:

    PYTHONPATH=src .venv/bin/python -c 'import json; from ruleshift.web_lab import verify_snapshot; print(verify_snapshot(json.load(open("research/www2027/G4_SAFARI_LIVE_TRACE_20260928.json"))))'

The expected result is verified=True, events=3, and final state hash
271b6e9c34f16da7. Open research/www2027/web_lab_ui.html directly
for the offline recorded fallback. Its formal-results table is static
read-only evidence; the offline page loads saved deterministic origin events
without re-executing them. `verify_snapshot` and the offline export verifier
are the independent replay checks.

The evaluation is limited to synthetic retail orders and two small open
models. Paired intervals describe variation over generated streams,
not reliability on real commerce websites.
