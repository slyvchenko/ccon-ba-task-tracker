# CCON BA review audit: 2026-10-27

[Canonical historical review register](PR_REVIEW_COMMENT_REGISTER.json): 148 original findings, each with its original GitHub comment URL, review thread, source file, priority, outcome and proof.

## Current verified historical review counts

- Original findings: **148**. Resolved: **124**. Still open: **24**, all **P2**; unresolved historical P1: **0**.
- **5** open threads are outdated in GitHub; outdated is not automatically fixed.
- Original opening snapshot: 78 resolved / 70 open. Subsequent follow-up has source-reviewed and closed **46** original threads, including **20** in this batch: 12 fixed in new PR #99, #100, #101 and #103, 8 already addressed by current-main code/tests.
- Exact proof is posted as replies to each original GitHub review thread; new PR-specific comments are not added to the 148 historical-original cohort.
- **All merged engineering PR #94 through #101 and #103 passed 4/4 synthetic CI jobs. PR #102 remains separately in CI and is not counted as a historical closure yet.** No independent UAT or production approval is claimed.

## Remaining reviews grouped by current source file

| File | Open findings |
|---|---:|
| `assets/dashboard.mjs` | 14 |
| `history_retention_preview.py` | 2 |
| `assets/dashboard.css` | 1 |
| `assets/manual-done-undo.mjs` | 1 |
| `assets/queue-dom.mjs` | 1 |
| `assets/visual-clarity.mjs` | 1 |
| `browser_e2e.py` | 1 |
| `docs/SQLITE_RETENTION_EVALUATION.md` | 1 |
| `tests/priority-property.test.mjs` | 1 |
| `weekly_workload.py` | 1 |

## Scope and acceptance boundary

- Canonical product backlog: **129 requirements** (40 code-IMPLEMENTED, 82 PARTIAL, 3 human GATE, 4 DEFERRED). All 129 human_acceptance entries remain NOT_RECORDED.
- [Review debt Issue #93](https://github.com/slyvchenko/ccon-ba-task-tracker/issues/93) stays open until 24 remaining original P2 findings are individually triaged and fixed/proved. Historical review resolution is not the same as user acceptance.
- [Release/UAT Issue #50](https://github.com/slyvchenko/ccon-ba-task-tracker/issues/50) remains `BLOCKED_INDEPENDENT_UAT` until authorized live BA-source gold cases, independent review and native Windows/Edge/NVDA/crash/8h acceptance. No real corporate payload, PNR, credentials or private records may enter this public repository.
- Merges update the repository, **not** an installed local Windows client.

Prioritize remaining issues with potential silent writes, false-ready status, missing warnings, recovery, evidence provenance, then noncritical UI/layout/test cases. Create focused PRs and regressions for reproducible bugs; resolve original threads only with merged proof.
