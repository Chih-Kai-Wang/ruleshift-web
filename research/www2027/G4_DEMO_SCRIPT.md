# RuleShift-Web: three-minute demonstration

The live mode is a laptop-bound HTTP service. The offline mode loads recorded
events that were independently verified when exported; its button does not
re-execute the origin. Neither mode generates a fresh language-model decision.

Before visitors arrive, start the local service from the project checkout:

    PYTHONPATH=src .venv/bin/uvicorn ruleshift.web_lab:create_app --factory --host 127.0.0.1 --port 8765

Open http://127.0.0.1:8765/lab/ and confirm the green Live local HTTP origin
badge. Open research/www2027/web_lab_ui.html directly in a second tab and
confirm the amber Recorded offline trace badge. Reset the live world before
each walkthrough. Keep the service bound to loopback because researcher
routes can publish policies without authentication.

**0:00–0:25 — Question.** A web agent holds a policy response. The website
publishes a new rule. Is the response fresh under HTTP, and does an action
still have authority at commit? Point to the origin state, client evidence,
and event timeline.

**0:25–1:10 — Stale evidence.** Select Purchase discount. Press Reset world,
Unconditional reload (P1, HTTP 200), Publish restrictive P2, Reuse fresh
cache, and Submit requested operation. Show HTTP 409, zero purchases, and
the three-event trace. Press Verify replay; expect three verified events.
If the two-minute cache lifetime has elapsed, reset and repeat promptly.

**1:10–1:45 — Revalidation.** Press Conditional GET. The changed policy
returns HTTP 200 with P2. An unchanged policy would return 304. Press Check
public eligibility · no action: denial needs no transaction. Explain that
a 304 validates one representation at the time of the GET; a publication
between validation and commit still requires the origin revision check.

**1:45–2:20 — Frozen study.** Scroll to Compare frozen study results. The
read-only table summarizes 3,200 paired model executions plus 1,600 separate
no-LLM decisions. In this one-relevant-source harness, source-dependent
validation ties all-source conditional validation while making four fewer
policy reads per task. Always refresh had higher observed accuracy; the Qwen
interval includes zero. Phi retains 685 response-level contract failures
after the predeclared adapter, all contradictory action/reason fields.

**2:20–2:50 — No-network fallback.** Switch to the amber offline tab.
Select No change · conditional 304 and press Load recorded intervention.
Inspect the preverified HTTP 200 read, 304 validation, and 201 purchase.
Then select Relevant change · reuse old cache for the 409 contrast.
Saved local Qwen development cases are visibly labelled as development,
not the held-out Colab evaluation.

**2:50–3:00 — Close.** The contribution is the inspectable Web workbench:
visitors vary policy publication, evidence validation, and commit timing,
then replay what happened. The study shows both the cost and limits of
memory checking.

If the live service fails, use only the amber offline tab and explicitly
label its branches as recorded deterministic events. The five-strategy
table remains available without a network connection.

On 2026-09-28, a fresh Safari run produced HTTP 200 read, HTTP 200
publication, and HTTP 409 purchase without mutation. Its downloaded
G4_SAFARI_LIVE_TRACE_20260928.json independently replayed three events
with final state hash 271b6e9c34f16da7. The modified table and offline
200→304→201 branch were also inspected in Safari. The offline button only
loads that saved branch; the separate verifier re-executes it.
