# PERF-08 / FOCUS-06: selected-task detail refresh contract

**Code implementation:** PR #55, runtime version 2.49.0. **Acceptance:** synthetic unit/Chromium tests only until native BA UAT completes.

## The old behavior
The previous `taskVersion()` used `latest.hash` or the global `generated_at`, then the selected task. A new Jira snapshot changing just one unrelated task therefore changed the detail version for every task. `load()` rerendered the selected detail, replaced its DOM and reissued GETs for evidence, questions, decisions, action plan, history, approved copy, and supplier ZIP state. On 500–1000 tasks this created avoidable network and focus churn.

## Contract in PR #55
- Detail content is keyed by **selected task content excluding its volatile `importedAt` timestamp**, not global import timestamp, queue position or metadata. The list still refreshes when anything changes. If only another task changes, the current detail DOM and its initialized nested sections remain unchanged. The visible import timestamp is updated in-place so provenance remains current.
- Changing the selected task's manual revision, source content, status or analysis still refreshes the detail.
- Each new detail DOM carries a render generation. Late GET responses for a previous generation, **even for the same task key**, cannot write to the newer detail's evidence/questions/decisions/actions/history/approved sections.
- No new view, tab, background job, external write, automatic email or Jira update. Client-side changes only; no caching of stale evidence across genuine selected task changes.
- Supplier ZIP loader already rejects obsolete per-load requests using its own request counter. Its explicit background status checks are not disabled by this change.

## Synthetic acceptance
`tests/detail-refresh-policy.test.mjs`: global-snapshot independence, current task mutation invalidation, same-key stale promise guard.
`browser_e2e.py`: Chromium importer changes another task, verifies the current input DOM is preserved with no repeat expensive selected-task GETs, then changes the current task and verifies a refresh/reload occurs.
`check_project.py` + GitHub Actions: Python/Node/release, Chromium E2E, native Windows unit, developer-only branch coverage.

## Still open
- 8-hour native Windows Chrome/Edge session, 100/500/1000 actual device p50/p95, memory and scroll/keyboard continuity.
- Manual note/caret recovery through crashes or conflicting tabs; genuine source-verified BA task UAT.
- Issue #50 independent live signoff. The PERF-08 backlog row stays **PARTIAL**, `human_acceptance=NOT_RECORDED`.
