# Three authority surfaces in one recorded intervention

This annotation refers to the actual Safari export in
`G4_SAFARI_LIVE_TRACE_20260928.json`. It is a single browser observation,
not a held-out model run. The `verify_snapshot` command in
`G4_REPRODUCIBILITY.md` re-executes its three origin events from the saved
initial state and checks responses and final state hash. The separate
`scripts/verify_offline_exports.py` checks the saved JS examples.

| Event | Client-held evidence | Origin rule | Commit result |
| --- | --- | --- | --- |
| 0: `GET /site/policies/discount`, `200` | P1 permits discount; revision `5c83f174615ef26c` | P1 | No transaction |
| 1: researcher publishes P2, `200` | Client still holds P1 | P2 denies discount; revision `67b16710a49c0b66` | No transaction |
| 2: purchase with P1 expected revision | Agent request still names P1 revision | P2 remains active | `409 policy_revision_changed`; purchase list remains empty |

The origin state hash after publication and after the rejected purchase is
identical: `271b6e9c34f16da7`. This supports the narrow observation that
this stale attempt did not mutate the transaction state. It does not show
that an agent avoided the attempt; the attempted purchase is event 2.

The workbench exposes all three views separately: the evidence cached by
the visitor's agent, the policy currently served by the HTTP origin, and
the application revision enforced at commit. HTTP validation, when used,
establishes the representation selected at the time of the GET. The
application revision guard handles a later change before the transaction.
The formal 3,200-task matrix publishes scheduled changes before each task's
evidence check and does not measure this validation-to-commit race.

The saved deterministic `race` branch in `web_lab_trace.js` separately shows
the within-task sequence: P1 read (`200`), permissive P3 publication,
conditional GET with an older validator returning P3 (`200`), restrictive P2
publication, then a purchase naming P3's revision rejected as
`409 policy_revision_changed`. Its final purchases list is empty and its
five events pass the same clean-state replay verifier. This is a recorded
demonstration intervention, not a held-out model decision or an HTTP `304`
sequence.
