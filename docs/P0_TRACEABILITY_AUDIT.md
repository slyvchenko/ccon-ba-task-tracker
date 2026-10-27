# P0 traceability audit: source/test pointers, not acceptance

This is a **read-only audit of existing modules and existing synthetic tests**, not a feature release. It preserves all 129 statuses and the release BLOCKED decision.

## Inspected existing pointers added

| Requirement | Source | Regression pointer |
|---|---|---|
| CORE-04, 0–100 factor scoring | `priority_score.py` | `tests/test_priority_score.py` |
| BA-03, compact verified context | `ba_briefing.py` | `tests/test_ba_briefing.py` |
| UX-01, original one-page BA Desk | `assets/dashboard.mjs` | `browser_e2e.py` |
| QUICK-01, single next action | `assets/fast-handoff.mjs` | `tests/fast-handoff.test.mjs` |
| FOCUS-01, selected task under filtering | `assets/queue-performance.mjs` | `tests/queue-performance.test.mjs` |
| PRIOR-01, manual XS–XL/UNKNOWN with provenance | `assets/effort-planning.mjs` | `tests/effort-planning.test.mjs` |
| PRIOR-02, verified sprint then WRITE hard lanes | `assets/task-rules.mjs` | `tests/priority-hard-lanes.test.mjs` |
| PERF-01, local SQLite revision | `desk_store.py` | `tests/test_json_response_cache.py` |
| PERF-02, revision-gated update | `assets/revision-policy.mjs` | `browser_e2e.py` |
| PERF-03, cached no-query filtering | `assets/queue-performance.mjs` | `tests/queue-performance.test.mjs` |
| REL-01, optimistic edit CAS | `desk_store.py` | `tests/test_manual_edit_cas.py` |
| QA-11, multi-tab edit conflicts | `desk_store.py` | `tests/test_manual_edit_cas.py` |

These are **navigation hints only**. A referenced file or test does not prove the entire business acceptance criterion, latency SLO, real Jira/CCON correctness, cross-tab Windows behavior, independent human review, or deployment readiness.

## Deliberately not mapped

- `EVD-05`: authorized automated supplier ZIP retrieval via local Codex is not demonstrated by a sufficiently precise code and regression pair. Do not claim it exists based on adjacent attachment download modules.
- `QA-02` and `QA-10`: require live, independent BA acceptance. Synthetic tests cannot replace their source verification or observed human timing.

## Deterministic result

- Total 129 unchanged: 40 code-reported IMPLEMENTED, 82 PARTIAL, 3 GATE, 4 DEFERRED.
- Source+test pointers: **66 → 78**. Requirements with no code pointer: **57 → 45**.
- Zero upgrades to `human_acceptance`; all remain `NOT_RECORDED`.
- `release_readiness.py --require-ready` remains fail-closed. Issue #50 remains open.

Once these code locators are mapped, the next meaningful action is an **authorized private BA/Windows acceptance**, not another speculative UI/dashboard feature.
