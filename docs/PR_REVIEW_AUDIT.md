# CCON BA: historical GitHub review audit (2026-10-27)

[Source-of-truth JSON register](PR_REVIEW_COMMENT_REGISTER.json): exact GitHub comment URL, PR, source path, review-thread ID, severity, disposition and next action for the original 148 findings.

## Verified result after PR #97

- **148 historical findings:** **104 resolved, 44 open**. All 44 remaining open findings are **P2**, no unresolved historical P1; **11** of these open threads are outdated, which does not by itself prove a fix.
- **26 additional original findings** source-reviewed and their original GitHub threads resolved on 2026-10-27: **8 addressed by new merged PR #94-97**; **18 already addressed by current-main code/tests**. The prior baseline was 78 resolved / 70 open.
- The historical cohort comprised 90 PR, 148 original comments. Newer PR review threads from #94-97 are not counted as original findings. The historical comment replies now include 26 verified follow-up replies.
- **44 open** remain `SOURCE_LEVEL_TRIAGE_REQUIRED`; code-level review, reproducer or explicit proof is still needed. Do not mark them DONE solely because a PR was merged or the thread is outdated.
- No release or BA signoff: **129 canonical requirements = 40 code-IMPLEMENTED / 82 PARTIAL / 3 GATE / 4 DEFERRED**. All 129 human acceptance fields remain NOT_RECORDED. Release remains `BLOCKED_INDEPENDENT_UAT` ([#50](https://github.com/slyvchenko/ccon-ba-task-tracker/issues/50)).

## Reviewed fixes (all listed PRs passed 4/4 synthetic quality jobs)

| PR | Original findings closed | Scope |
|---|---:|---|
| [#85](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/85) | 4 | Pointers, symlinks, SQLite journal, draft overflow |
| [#86](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/86) | 2 | Browser storage, clock rollback |
| [#87](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/87) | 1 | Cross-tab CAS on focused refresh |
| [#88](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/88) | 2 | UTF-16 DTD, XML namespace shapes |
| [#89](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/89) | 1 | QA-13 mandatory UAT routing |
| [#90](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/90) | 2 | Jira attachment parent links and report cap |
| [#91](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/91) | 2 | Symlink ancestors in diagnostics |
| [#94](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/94) | 3 | Departed Jira jobs, consistent SQLite views, backup timestamp underflow |
| [#95](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/95) | 1 | Stale supplier ZIP warning styling |
| [#96](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/96) | 2 | Rovo standalone description rules and observed event dates |
| [#97](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/97) | 2 | Error-budget route normalization and p95 rank |

The other 18 source-verification closures link original GitHub threads to current-main files and tests: two evidence fixture cases in #22, backlog counts in #64-65, regex coverage #74, NTFS junction detection #75, seven historical workload findings #67 and five HTTP-budget findings #68. Review replies document the exact evidence; the WAL read-only guarantee from #67 remains **open**.

## Remaining historical P2 findings by file

| File | Open findings |
|---|---:|
| `assets/dashboard.mjs` | 14 |
| `ba_quality_gate.py` | 3 |
| `browser_e2e.py` | 3 |
| `confluence_local.py` | 3 |
| `assets/visual-clarity.mjs` | 2 |
| `ba_output_checks.py` | 2 |
| `history_retention_preview.py` | 2 |
| `local_diagnostics.py` | 2 |
| `sqlite_mode_study.py` | 2 |
| `apply_analysis.py` | 1 |
| `assets/dashboard.css` | 1 |
| `assets/manual-done-undo.mjs` | 1 |
| `assets/queue-dom.mjs` | 1 |
| `ba_compactness.py` | 1 |

Other files: `docs/SQLITE_RETENTION_EVALUATION.md` (1), `model_analysis.py` (1), `release_integrity.py` (1), `tests/priority-property.test.mjs` (1), `tests/test_sqlite_retention_study.py` (1), `weekly_workload.py` (1).

## Triage and release boundary

Prioritize security/privacy and lost writes, false BA/source facts, then user-action correctness, followed by performance, tests and documentation. Each verified defect needs a small scoped fix PR, regression and passing CI; already-fixed findings require exact source/test proof and an original-thread reply.

**Do not claim release-ready from CI:** complete private 26-case independent BA gold review with live authorized Jira/Kibana/CCON access, then native Windows/Edge/NVDA/crash/8h acceptance and owner signoff. No real payloads, tokens, PNRs, or private test files belong in this public repository. Merging to main does not update a local Windows installation.
