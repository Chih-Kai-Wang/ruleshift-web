# G4 manuscript claim audit — 2026-09-28

This is an author-side cross-check of the current manuscript, **not** an
independent scientific review or a substitute for author approval. The
held-out records and frozen protocol were not altered for this check.

| Manuscript claim | Direct evidence checked | Assessment |
| --- | --- | --- |
| 3,200 model tasks and 1,600 no-LLM decisions | `G3_FORMAL_{QWEN,PHI,CONTROL}_AUDIT.json`: each has 200 streams/arms, five strategy cells of 320 tasks, and no recorded failures | Matches; do not call the 200 control arms “200 tasks” |
| Table 2 correct counts | Recomputed from the three auditors' `by_strategy[*].correct`: Qwen 273/274/287/284/284; Phi 141/141/223/195/195; control 300/300/320/320/320 in table order | Matches; all denominators 320 |
| Table 3 request counts | `by_strategy[*].agent_http_requests`: Qwen 737/794/1017/2300/1020; Phi 555/555/890/2149/869 in table order | Matches; counts are total agent requests over 320 tasks per cell |
| Source-dependent ties conditional-all accuracy and saves four policy reads per task | Qwen 284=284, Phi 195=195; `policy_reads` is 520 versus 1800 for each model; both differences are 1280/320=4 | Structural result from one declared relevant source versus five, not a generalized efficiency gain |
| Always-refresh observed accuracy is higher | Qwen 287>284; Phi 223>195; paired source-minus-always intervals in audit are [-1.875,0] and [-16.875,-2.5] percentage points | Matches; Qwen interval touches zero, so avoid claiming a clear statistical separation there |
| Retrieval contrast and uncertainty | Audit `paired` entries: Qwen +3.4375 pp [1.5625,5.3125]; Phi +16.875 pp [11.875,22.1875] | Manuscript rounding matches |
| Phi response-contract failures | Sum of response-level audit counters: 1,626 raw and 685 after the predeclared Markdown-fence adapter; Qwen zero. The 685 residual raw responses were independently reparsed as JSON; all have contradictory `attempt`/`reason` fields | Matches; these include retries, **not** 685 distinct failed tasks or malformed JSON |
| No invalid commits or failed arms | Every audit strategy cell has `invalid_commits=0`; all three audits have `recorded_failures=[]` | Matches; this is a guarded synthetic origin, not proof that the models never attempted invalid actions |
| Frozen methods and model provenance | `G3_FROZEN_PROTOCOL.json` SHA-256 `3ef328fbdbb02ff2862445751f8a4f261a2e15014253f81cde72a4a8980f34d8`; records greedy float16, pinned revisions, L4, 10,000 stratified bootstrap draws | Matches the protocol and manuscript |
| Offline example and local-model traces | `scripts/verify_offline_exports.py` readback: seven deterministic branches, 41 system events, eight local MLX development runs, 16 verified traces | Matches; static replay is not a fresh LLM decision |
| Browser intervention | `G4_SAFARI_LIVE_TRACE_20260928.json` independently replays three events with a final state hash of `271b6e9c34f16da7`; `G4_ANNOTATED_TRACE.md` gives the event-by-event interpretation | Supports the single newly observed 200 read, 200 publication, 409 rejected action; the older seven browser cases remain separately reported in `G2_BROWSER_QA.md` |

The main interpretation is appropriately limited: validation of a relevant
source makes fewer policy reads than validating every source by construction,
but does not improve accuracy over unconditional refresh here. Total HTTP
requests include attempted transactions, so lower totals can reflect lower
completion. The agent's response to
evidence timestamps is a plausible explanation for three Qwen paired misses,
not a causal proof that conditional HTTP validation is faulty. Generated
stream confidence intervals do not estimate performance on live commercial
sites. The non-LLM controller is a strong environment-specific reference,
not a general-purpose web agent.

Reference metadata for STALE, EvoArena, PlanFence, and EnvTrust was checked
against the corresponding arXiv abstract pages on 2026-09-28. The official
Demo call specifies a nonanonymous English ACM double-column submission of
at most four pages including references, an ethical-use section, and
in-person presentation if accepted. The current PDF is three pages, but its
author block is a placeholder. Independent Astra/high and Sol/high reviewers
returned major scientific revisions and concrete package/UI repairs. Their
focused recheck is recorded separately in `G4_INDEPENDENT_REVIEW.md`;
no claim of acceptance or publication is warranted.
