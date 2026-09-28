# Frozen G3 result — 2026-09-28

The held-out Colab L4 matrix is complete: **3,200 model-task executions**
(2 pinned models × 5 strategies × 40 eight-task streams), plus a separately
audited **1,600 no-LLM control decisions** (5 strategies × the same 40
streams). All 600 stream/strategy arms are present across the three
checkpoints. The independent auditor found **zero failed arms, invalid
commits, or origin-replay disagreements**. The frozen protocol was written
before either held-out model run; its SHA-256 is
`3ef328fbdbb02ff2862445751f8a4f261a2e15014253f81cde72a4a8980f34d8`.

The user's proposed “3,400” count mixes units: the planned experiment has
3,200 **model tasks** plus 200 **control arms**, each with eight decisions.
The full number of evaluated decisions is therefore 4,800, with 3,200 of
them made by the two language models. Development preflights are excluded.

| Strategy | Qwen correct / 320 | Phi correct / 320 | No-LLM correct / 320 | Qwen / Phi / control agent HTTP requests |
|---|---:|---:|---:|---:|
| Retrieval | 273 | 141 | 300 | 737 / 555 / 684 |
| v1 selective | 274 | 141 | 300 | 794 / 555 / 684 |
| Always refresh | **287** | **223** | **320** | 1,017 / 890 / 984 |
| Conditional all | 284 | 195 | **320** | 2,300 / 2,149 / 2,264 |
| Source dependent | 284 | 195 | **320** | 1,020 / 869 / 984 |

The primary endpoint is correct final decision **and** actual state change,
not merely a well-formed answer. All strategies had the same task streams,
starting site state, public observations, and action budget. The registered
comparisons use 40 paired eight-task streams, stratified by four scenarios,
with 10,000 bootstrap draws and two-sided 95% percentile intervals.

For **Qwen**, source dependent exceeded retrieval by 3.44 percentage points
(95% interval 1.56–5.31) and v1 selective by 3.13 points (1.25–5.00).
It tied conditional all exactly in accuracy while saving four HTTP requests
per task. Always refresh was 0.94 points better than source dependent
(source-minus-always interval −1.88 to 0.00), so this experiment does not
show a universal accuracy gain for the proposed method.

For **Phi**, source dependent exceeded retrieval/v1 selective by 16.88
points (11.88–22.19), tied conditional all, and saved four HTTP requests
per task versus conditional all. Always refresh beat source dependent by
8.75 points (source-minus-always interval −16.88 to −2.50). The result is
not a clean cross-model quality ranking: Phi used a predeclared exact
Markdown-fence adapter selected on development data, whereas Qwen used the
strict parser. Phi still produced 1,626 raw and 685 effective
response-level format errors over its 1,600 task executions, versus zero
for Qwen. These counts include retry responses and must not be reported as
numbers of distinct failed tasks.

The strong non-LLM controller reached 320/320 for source dependent,
conditional all, and always refresh, and 300/320 for retrieval and v1
selective. This bounds the model-related deficits in the controlled task;
the prototype should be presented as an **inspectable evaluation and replay
workbench**, not as evidence that the proposed controller beats all strong
alternatives. Retrieval and v1 selective had stale-memory errors in all
three controller classes; source dependent, conditional all, and always
refresh had none in this matrix. The transaction revision guard prevented
invalid commits in every arm, including those with incorrect model choices.

Qwen's three source-dependent misses relative to always refresh were
address-age decisions. In each matched pair, the policy body and revision
were identical, while the evidence's `observed_at` timestamp differed after
conditional validation versus a full GET. The raw model inputs and outputs
are preserved. This is a prompt/provenance sensitivity observation; it does
not show that HTTP conditional validation supplied an obsolete policy.

The two CUDA runs used pinned model revisions, greedy float16 inference,
no CPU/disk offload, and the same NVIDIA L4. Their script wall times were
930.53 and 993.06 seconds; their summaries and raw SQLite files are saved
separately. The Colab balance displayed 186.91 CCU before formal execution
and 185.37 after. The 1.54-unit displayed difference includes setup and
idle time, so it is not an exact task charge. It leaves substantially more
than the predeclared 20% reserve.

## Audit trail

- Frozen package: `ruleshift-web-g3-formal.zip`, SHA-256
  `6d0375e27d1e2f7e3e21405b494c3c6a5ce4f6bdb5b90bd14ce8c74c462bbfbb`.
- Qwen transferred zip: `ruleshift-g3-formal-qwen-20260928.zip`, SHA-256
  `996254968d207c739648e3a8ad22fead891e6e99db26ac45c9cc017da0d9f9f1`;
  checkpoint and independent result in `g3-formal-qwen-20260928/` and
  `G3_FORMAL_QWEN_AUDIT.json`.
- Phi transferred zip: `ruleshift-g3-formal-phi-20260928.zip`, SHA-256
  `61f23d738b6df7d43ef167269ae5bce45a2b66332466cb8c119ac98adb8e84ed`;
  checkpoint and independent result in `g3-formal-phi-20260928/` and
  `G3_FORMAL_PHI_AUDIT.json`.
- Separate control: `g3-formal-control-20260928/` and
  `G3_FORMAL_CONTROL_AUDIT.json`.
- Colab resource observation: `G3_FORMAL_RESOURCE_OBSERVATION.json`.

All conclusions are limited to two small open models and a synthetic,
controlled retail-policy site. The paired intervals quantify variation
over these generated streams, not deployment uncertainty on real websites.
The site/workbench contribution and the final four-page Demo manuscript
still require independent scientific and venue review.
