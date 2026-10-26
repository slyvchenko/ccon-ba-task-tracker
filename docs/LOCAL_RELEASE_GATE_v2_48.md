# v2.48: code closeout vs real release readiness

**Status: CODE PACKAGES COMPLETE SUBJECT TO PR #48 MERGE, PRODUCTION ACCEPTANCE NOT APPROVED.** The original single-BA local dashboard is preserved. This file is a bounded closeout and operator runbook, **not** independent business approval.

## What is actually evidenced

The recommended scoped engineering package after the original #38 consists of PR **#39–48**. PR #39 established an auditable ledger and #40–47 provide the engineering safeguards and regressions detailed in each review. PR #48 adds a fail-closed release-readiness inventory and requires CI plus an explicit **separate** private acceptance phase. These are git and synthetic-test accomplishments, **not evidence of live booking success, actual supplier contract compliance or deployed Windows parity**.

The canonical inventory remains **129 requirements**, including **44 P0**, **54 P1**, **27 P2**, and **4 P3**, rather than a claim of 129 delivered features. The original source status breakdown is 37 IMPLEMENTED (as reported in Markdown), 52 PARTIAL, 32 PLANNED, 1 NEXT, 3 GATE, 4 DEFERRED. The presence of a code/test locator does **not** mean a source-backed feature is accepted. All 129 generated `human_acceptance` fields are `NOT_RECORDED` at the time of #48. The four optional cloud P3 items are deferred and do not authorize them to be erased.

### Hard real-world gates before local production signoff

| Gate | Current public evidence | What must happen privately |
|---|---|---|
| QA-02: Jira/Kibana/CCON live source access | NOT VERIFIED | Authorized user inspects real flows, exact REST/supplier RQ/RS, rejects ambiguous/missing evidence |
| QA-03: 20–30 BA gold cases | NOT RECORDED | Independent reference and source-verified 26-case sample (READY/WRITE/WAIT/DECIDE/DEEP/ERROR); zero critical false-ready |
| QA-10: human UX and priority workflow | NOT RECORDED | TTNA/TTSH and safe handoff measured on real cases; verified active sprint/WRITE correctness |
| QA-13: private provenance and QA report | NOT RECORDED | Confirm real evidence versions, privacy, anonymous aggregate results, signed private reviewer findings |
| Windows SQLite crash/restore | NOT VERIFIED | Synthetic test instance under Windows: actual killed process, WAL/lock, rescue and complete manual-state restore |
| Windows Edge/NVDA/zoom | NOT VERIFIED | Native Chrome/Edge at 100/200/400% zoom, keyboard, NVDA, forced colors, no hidden critical controls |
| 8h Windows session | NOT VERIFIED | Local Task Scheduler instance, session recovery, memory/input/focus and reconnect behavior validated over sustained operation |

No green GitHub Action can substitute for these seven gates. `python release_readiness.py --check` validates public inventory **structure**, prints `BLOCKED_INDEPENDENT_UAT`, and returns 0 solely for CI; it **does not** approve release. `python release_readiness.py --require-ready` deliberately returns a nonzero code until independent private approval is supported by a future explicit verification workflow. Even injecting `PASSED` strings into public JSON cannot make the current gate return READY.

## Exact operator handoff

1. Make sure #48 and quality jobs are green on `main`. GitHub merge does **not** change an existing local Windows application or scheduled launcher.
2. Close the local server and tabs safely. Make a verified private SQLite backup using `local_backup.py backup` then `verify`. Protect it with Windows disk encryption/ACL; **do not commit** DB, supplier ZIP, PNR, Jira descriptions, emails, tokens or private screenshots.
3. On the Windows device, deliberately update the installed local application from the reviewed revision. Review the launcher/Task Scheduler pointing to the expected folder and correct Python version. Retain a rollback copy of the old application and private DB backup. Never blindly overwrite the live `data/`, `backups/`, `ba_state.db` or `inbox/`.
4. Start and validate that the local service uses the expected version, same personal Jira scope and active board, and that manual notes, effort, draft, action/history and approved description survive restart. Verify a fresh snapshot does not silently overwrite unsaved edits.
5. Execute the live BA and Windows acceptance matrix **privately** using `docs/BA_GOLD_CASE_ACCEPTANCE.md`, `docs/PRIVATE_BACKUP_RESTORE.md` and `docs/A11Y_FINAL_SCOPE_REVIEW.md`. Record human signoff in an organization-approved private location, not the GitHub ledger.
6. Only after independent approval may product ownership make a subsequent explicit release decision. This repository cannot infer live approval from CI or from a self-edited `human_acceptance` string.

## Optional and potentially redundant scope

Avoid adding second Quick/Deep screens, automated Jira status writes or supplier auto-send as a shortcut to a 100% completion number. Consider the existing 16 VIS hypotheses and P2 candidates (quick templates, manual pinning, WIP/error dashboards, CSS refactor) **scope-review**, not forgotten and not automatically delivered. Separate cloud/SSO/PostgreSQL is still a distinct optional product decision. Human usage and critical facts must decide whether a feature is omitted, consolidated or genuinely required.

## What the scripts check

`backlog_audit.py --check` compares the deterministic ledger with the canonical Markdown requirements and path pointers. `release_readiness.py --check` validates all IDs, status counts, 44 P0 priorities and required QA gates, and explicitly refuses business release approval. `check_project.py` runs both structural checks plus Python/Node and synthetic performance checks. `browser_e2e.py` separately runs synthetic Chromium. All are suitable as **engineering** gates only; live supplier and Windows UAT remain manual.
