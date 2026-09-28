# Independent read-only G3 review assessment — 2026-09-28

Antigravity was asked to examine only the G3 protocol, stream runner, and
auditor, without editing files or opening held-out results. Its findings
were checked against the current source and shipped preflight archive.

1. **Confirmed and fixed:** the no-LLM control used schedule slot 2 while
   `balanced_schedule` accepted only 0 and 1. The scheduler now accepts slot
   2, and its 200-arm completeness and balance are covered by
   `tests/test_web_schedule.py`. This occurred before any protocol freeze.
2. **Archive-hash warning rejected for the shipped preflight:** the review
   compared today's formal runner, which hashes `web_schedule.py`, with an
   older shipped preflight zip. The zip contains its own earlier runner,
   whose hash calculation never included `web_schedule.py`; the freeze script
   reconstructs that earlier six-file hash in the same order. The zip is
   intentionally immutable and its checksum passed. Repacking it with the
   current runner would invalidate a package already handed to the user.
3. **Commit-source difference retained as an audit check:** the runner scores
   non-purchase completion from the simulator's final order state, while the
   independent auditor reconstructs completion from successful origin events.
   A disagreement correctly fails the audit. A failure after mutation but
   before event recording raises out of the stream and is journaled as a
   failed arm rather than a completed score.
4. **Parser asymmetry disclosed:** Phi receives the exact Markdown-fence
   adapter selected on G2 development evidence; Qwen remains strict. Every
   strategy within a model uses the same adapter, and the primary contrasts
   are within-model. Raw and adapted format-error counts remain separate.
   Cross-model score differences must not be interpreted as pure model-quality
   differences. The review incorrectly named Qwen-2.5-Coder-7B; the pinned
   evaluated model is Qwen3-4B-Instruct-2507.

The review did not examine user-operated Colab G3 preflight or formal raw
records, because none were available. It therefore cannot certify GPU
execution or publication-ready results.
