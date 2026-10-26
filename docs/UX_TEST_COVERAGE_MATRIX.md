# CCON BA Desk: end-to-end UX, functional, performance and reliability test matrix

**Contract:** never infer a business-correct answer from static CI. Synthetic test cases must contain no real corporate data. `docs/PRODUCT_BACKLOG.md` lists feature ownership and status, while this document maps **acceptance behavior → automated tests → remaining human UAT**.

## A. Critical paths, including 2-minute small-task execution

| ID | Critical task journey | Minimum acceptance | Automated coverage | Remaining hands-on UAT |
|---|---|---|---|---|
| J-01 | Open desk from Windows shortcut | Show queue without extra installs; no unhandled exception | static release + HTTP smoke | Windows 10/11, Python 3.10/3.13, first-run and restart |
| J-02 | Fast triage of 30+ tasks | Sprint ahead of backlog, genuine WRITE first in same lane, no lost selection | task_rules.test.mjs; task-perf.test.mjs | Live priority comprehension, 3–5 sec scan |
| J-03 | Quick READY task | Next action obvious, copy prepared task text, no premature Jira Done | BA quality tests, click copy behavior | Time-to-safe-handoff 1–5 min with human |
| J-04 | Quick WRITE task | Correct email draft, no unverified attachment, manual send only | email and ZIP tests | Real mail client and supplier ZIP, no auto-send |
| J-05 | Short blocker | WAIT/owner/follow-up visible, no repeat unnecessary letter | questions/action tests | Live issue with waiting response |
| J-06 | Deep NDC rebooking issue | Context/contract/evidence/QA reachable without long re-search | evidence + quality gate tests | 60 min analyst walkthrough |
| J-07 | Resume after interruption | Unsaved note/draft kept, cursor and focus restored, stale clearly shown | desk save, JS recovery currently PARTIAL | 2 tabs, 30-minute interruption, restart |
| J-08 | Complete & Next | Manual state persisted, next ranked task selected, no external Jira write | desk HTTP, JS rule tests | Keyboard + selection/scroll feedback |
| J-09 | Bulk supplier letters | Only eligible draft previews, manual recipients reviewed | bulk email/tests, log tests | 5 mixed suppliers, wrong ZIP and missing recipient |
| J-10 | Search technical field/PNR/method | Same matches with empty and technical search; quick results | task_rules.test.mjs, task-perf.test.mjs | Unicode, >500 rich tasks, responsive latency |

## B. Source truth, workflow and data safety

| ID | Critical invariant | Automated coverage | Manual / risk remaining |
|---|---|---|---|
| D-01 | Only personal Jira queue, linked issues read-only contextual | Jira sync tests | Real account and board scope |
| D-02 | Unverified sprint never masquerades as active | JS priorities / sprint_priority tests | Real Jira sprint changes |
| D-03 | No invented IF/THEN/AND/OR, field capitalization, method, QA | ba_quality_gate, output checks | 20–30 human gold cases |
| D-04 | External URL is a reference, not proof of read content | source registry, local crosscheck | Supplier contract semantics |
| D-05 | Local ZIP selected supplier only, REST/errors internal | logs, supplier tests | Real Kibana download |
| D-06 | Data never sent to unapproved model/URL | cloud_security, prompt_safety | Security/DLP approval and live audit |
| D-07 | Human edits survive snapshot import | desk, apply analysis tests | Multi-tab CAS unresolved |
| D-08 | Safe STOP/RESTART during active edits | storage/lock tests; performance test | Windows and power-loss UAT |
| D-09 | Invalid snapshot leaves prior DB intact | test_desk, test_local_performance | Unexpected filesystem/antivirus behavior |
| D-10 | Quality warnings never misreported as human validation | evaluation + QA tests | Gold-case human review |
| D-11 | Read-only Jira/Confluence; letter draft not sent | workflow integration | Official UAT with permitted identity |
| D-12 | Cases from other suppliers not merged by guessed PNR | evidence regression tests | Real multi-provider logs |

## C. Local speed / liveness / concurrency

| ID | Situation | Assertion / expected result | Automated coverage | Remaining |
|---|---|---|---|---|
| P-01 | Initial GET /api/tasks | Full snapshot includes same current revision, tasks, error | test_local_performance | browser timing |
| P-02 | Idle GET /api/tasks/revision | Constant-size version payload, no Jira data, full fetch bypass on same revision | test_local_performance, task-perf.test.mjs | real traffic trace |
| P-03 | One manual save | Exactly one transactional +1 revision and durable data | test_local_performance | multi-tab visual feedback |
| P-04 | Valid new import | Exactly one +1 revision and current task snapshot | test_local_performance | watcher race |
| P-05 | Duplicate import | No version bump / no edit overwrite | test_local_performance | operating Windows watcher |
| P-06 | Invalid import/unknown task | No revision bump / no partial write | test_local_performance | full-disk and permissions |
| P-07 | Parallel acknowledged saves | All serialized, monotonic count, no error | test_local_performance | cross-process CAS planned |
| P-08 | Restart | Same DB revision and saved note/draft recovered | test_local_performance | crash during transaction |
| P-09 | No search query | Do not access large technical deep descriptions | task-perf.test.mjs | CPU profiling |
| P-10 | Existing sprint and WAIT priority | Relative hard priority intact after optimization | task-perf.test.mjs | real day workflow |
| P-11 | Hidden tab | No periodic task/log/report/health fetch; resume immediately on focus | JS implementation; manual UAT required | headless browser test next |
| P-12 | Revision request failed | Actionable error, no false stale success | JS fail-open policy; manual UAT | server restart and offline |
| P-13 | Large synthetic 100/500/1000 | Repeatable p50/p95 and response-byte metrics, no fragile CI hard timing limit | performance_smoke.py | Windows/browser benchmark |
| P-14 | Rapid typing/search | No foreground input stall and correct Unicode matching | filter tests | DevTools search p95 profiling |
| P-15 | Deep card selection while changing snapshot | Dirty forms untouched and original edit preserved | apply/import tests | keyboard focus/scroll & React-free re-render |
| P-16 | 8-hour browser session | Memory/observers/event handlers stable | not covered | DevTools heap/performance |
| P-17 | Concurrent two browser tabs | Detect conflicts, prevent silent last-writer-wins | **NOT YET IMPLEMENTED** | design + code + tests P0 |
| P-18 | Partial import or corrupt SQLite | Recovery runbook + backup; data not silently reset | import tests partial | corruption/recovery drill |

## D. UI/accessibility/localization checks to implement before claiming success

| ID | Scenario | Acceptance requirement |
|---|---|---|
| A-01 | Keyboard-only | Navigate queue, open task, copy, save and next with visible focus, no mouse |
| A-02 | Screen reader | Semantic task list, headings, labels, live regions not excessively chatty, role/status |
| A-03 | Mobile 320 / tablet 768 / desktop 1440 | No horizontal scroll clipping a primary action; preserve readable task context |
| A-04 | 200% and 400% zoom | Task action and Save accessible, no overlapped buttons |
| A-05 | Windows High Contrast/forced-colors | State/disabled/focus differentiated without relying on colors |
| A-06 | Browser input with long technical field | Wrap/scroll safely, never truncate copied technical values |
| A-07 | Empty states | Distinguish no tasks, no matches, no proof, stale, and backend error |
| A-08 | Localization | UA interface, English technical Jira draft, stable field spelling, no accidental translation |
| A-09 | Hover/touch | Primary controls accessible to touch and keyboard, tooltips not essential |
| A-10 | Reduced motion | No mandatory animation delays; avoid scroll hijack |
| A-11 | Dialog | Bulk-email modal traps/focus-returns correctly, escape and destructive confirmation |
| A-12 | Feedback | No false Saved or Sent; clear disable/retry; status errors actionable |
| A-13 | Priority explanation | Sprint/WRITE/score/blocker reason visible and user trusts order |
| A-14 | Task switching | Dirty form and selected state persist even when new snapshot arrives |

## E. QA execution tiers

1. **Every PR:** Python unittest + Node test + syntax + packaged release + Compose, all green. New tests need to appear in release_manifest.json.
2. **Weekly local smoke:** 5 synthetic personas and 20–50 task walkthrough with ordinary browser; check focus, scroll, Save/Next, changes in card density.
3. **Pre-release performance gate:** synthetic 100/500/1000 tasks on named Windows hardware + browser DevTools trace, compare p50/p95 and error counts, record observed baseline in private notes, *not invented metrics in repo*.
4. **Real BA semantic gold-set:** 20–30 independently reviewed real issue analyses in gitignored data/evaluation; zero critical false assertions and measured time-to-handoff, no model self-grading.
5. **Security/production gate:** corporate authorized Jira/Confluence/Kibana and approved AI only, PII-safe, no Jira mutation, no send mail, no accidental provider XML disclosure.
6. **Chaos/recovery:** duplicate import, stale Jira, inaccessible server, SQLite locked, two tabs, browser close, power loss, Windows antivirus/file locks, missing ZIP/PDF, ZIP tamper, unsupported model.

## F. A test inventory is not code coverage

This table names regression contracts, not a line/branch coverage percentage. A coverage report requires instrumented line/branch measurement (for example `coverage.py` if approved as **dev-only** dependency), otherwise **do not claim 100%**. Node built-in coverage may be added in CI with a lower bound only after an observed baseline; DOM E2E should use an organization-approved browser test runner. Avoid brittle string-grep snapshots as a substitute for behavioral tests. Track every backlog item with test cases and actual evidence of adoption.

## G. Minimum launch checklist

- [ ] Baseline screenshot/traces, desktop + narrow viewport
- [ ] All critical Python/Node integration tests pass and release ZIP starts offline
- [ ] Windows 100/500/1000-task p50/p95 measured with documented hardware
- [ ] No skipped/false priority, no quick-task handoff incorrectly marked Done
- [ ] Manual edits persist across save / import / restart / interruption
- [ ] 20–30 real Jira gold-case human scores complete, factuality gate passed
- [ ] Browser and corporate source UAT approved, secrets remain private
- [ ] Release can be rolled back without destroying SQLite/manual state

## v2.28: quick-turnaround workflow tests

The new `tests/fast-handoff.test.mjs` covers deterministic one-analyst archetypes: ready/checked draft, WRITE needing a genuinely sent manual email, deep REVIEW, BLOCKED/NEEDS_REVIEW gate, stale Jira context, WAIT, manual DONE/archived, active sprint versus backlog, unknown scores, and task immutability. These tests check **policy**, not time-to-handoff or the final HTML layout.

Existing `check_project.py` automatically includes this Node test. `assets/fast-handoff.mjs` is served from the static allowlist and bundled in the offline release manifest. UI controls retain existing keyboard semantics (native buttons and `details`), but real Chrome/Edge keyboard and screen-reader UAT remain open.

Manual UAT to close #28: run 5 independent task archetypes in the locally installed Windows app; record task selection → understood next action → copied verified artifact → *actual manual* Jira/email handoff → Done→Next (p50/p95), then compare with v2.27. Confirm that canceling Done leaves the current task intact and that saved notes/drafts persist through focus changes, conflicts and refreshed snapshots. Do not report speed improvements or factual accuracy until measured and independently reviewed.

## v2.29: effort/quick-win test expansion

- `tests/effort-planning.test.mjs` checks all manual bands, provenance, no-fabrication for stale/WAIT/DONE/archive, complex rules, missing proof, draft completeness, 180 synthetic status/signal/sprint/score combinations × six band variations against unchanged `rankTasks`, and immutability.
- `tests/test_effort_persistence.py` checks `manual_effort` SQLite migration, save/restart/duplicate import, revision CAS and stale tab conflict, status-only + email draft preservation, invalid values atomic rejection and return to UNKNOWN.
- CI is intentionally free of real Jira descriptions/logs/PNR/personal data. Confirm in the actual installed Chrome/Edge app that select+Save are keyboard accessible, manual estimate survives browser restart and dual-tab conflicts, and quick indicators are not interpreted as priority overrides.
- BA gold-set acceptance remains **open**. Independently time 20–30 cases and compare predicted effort bands with actual time, incorrect >1-band outliers, interruptions, blocking work displacement and false-ready. Do not report speed gains or estimation accuracy solely from synthetic tests.

## v2.30: keyboard focus, interruption and truthful status coverage

Added `tests/focus-navigation.test.mjs` (shortcut map, editable target, IME and dialog guards; queue wrap without priority mutation; semantic disclosure matching even if sections reorder; cursor restoration without overwriting text; private view-state sanitization). Existing HTTP/SQLite CAS tests still cover concurrent writes and crash restart semantics. The UI now includes an in-place keyboard guide, alertable saving/unsaved/conflict states and native-dialog focus return.

**Not a DOM test suite.** Windows Chrome/Edge keyboard-only navigation, focus order under rerenders, Ctrl+Enter inside all fields, Escape dialog return, 200/400% zoom, screen reader status announcements, private localStorage cross-tab collisions and actual time-to-resume remain unverified. `docs/FOCUS_KEYBOARD_UX.md` has a stepwise UAT checklist; capture observations and action counts before closing FOCUS-02/03/06, UI-06, A11Y-01/04.

## v2.31: large-queue perf and concurrency regression

- `tests/queue-performance.test.mjs`: exact **legacy** vs cached queue result parity on 100/500/1000 synthetic Jira tasks across free-text/Unicode, filter, sprint and signal variants; rerank after in-place manual change; snapshot identity invalidation, index-once behavior, debounce flush/cancel.
- `tests/test_json_response_cache.py`: cached HTTP payload identical to `Desk.view()`, immutable cache identity on equal revision, CAS save/import/error and second Desk process invalidation, concurrent readers/writer with complete JSON.
- `performance_smoke.py`: SQLite `view` vs single-row `revision` vs cached `serializedHttp` p50/p95 and payload bytes (synthetic only).
- `queue_benchmark.mjs`: uncached vs indexed cold/warm Node search p50/p95, explicit baseline parity, 100/500/1000 synthetic cases.
- **CI smoke** runs short benchmarks after deterministic Python/Node/release tests, printing metrics only. No milliseconds hard limit on shared runner. Real browser/Windows, accessibility, scroll and 8-hour heap/memory runs are **NOT** covered and remain QA-09/PERF-05/07 UAT gates.

## v2.32: local private backup and crash-state regressions

`tests/test_local_backup.py` exercises complete backup/restore of synthetic notes, email draft, manual effort and revisions; rescue before overwrite; SHA mismatch and invalid confirmation; live process-lock restore refusal; symlink/path checks; seven-backup rotation; invalid Jira snapshot; supported legacy SQLite backup before migration; changed/unchanged watcher retry and recovery without repeated attempts. Existing CAS tests still prove no last-write-wins while the server operates normally.

UI now shows authenticated local backup timestamp/revision and snapshot-watcher state in existing **Data** dropdown, not an external browser download. No file body route, no unconfirmed Jira/email action. CI tests are synthetic only; they do not prove Windows ACL, virus scanner concurrency, hard power-loss, browser localStorage recovery, 400% zoom, assistive reading or 8h stability. Human UAT instructions in `docs/PRIVATE_BACKUP_RESTORE.md` are explicit gates before marking REL-03/04/05 fully DONE.

## v2.33: tab-isolated drafts and accessible queue acceptance

`tests/draft-recovery.test.mjs` covers independent tabs, cloned-tab rotation, same-tab reload, pre-v3 localStorage migration, manual orphan recovery with unsaved collision refusal, 30-day consent-based cleanup, corrupted records, bounded field validation and simulated quota/storage denial. Original `tests/manual-edit-policy.test.mjs` and `tests/test_manual_edit_cas.py` still verify per-task CAS/409 protection at the actual HTTP/SQLite layer.

The existing Data menu now exposes draft-recovery actions. Queue selection uses one polite aria-live announcer and a labeled region; 320px CSS, forced colors and reduced-motion additions have **no claimed automated pixel/AT proof**. Windows Chrome/Edge Duplicate Tab, NVDA, 200–400% zoom, privacy and 8-hour memory/endurance require real human UAT before closing SEC-04/A11Y-02/03/05/QA-12/15. `docs/BROWSER_RECOVERY_ACCESSIBILITY.md` provides the test cases.

## v2.34: real Chromium DOM checks, short endurance and reconnection

- `browser_e2e.py` is real Playwright Chromium HTTP/DOM E2E: synthetic active sprint/WRITE order, note Save/CAS, Alt+Down selection, duplicate task from two tabs + reload + 409, modal Escape without send, offline GET fail→recover without auto-POST, background snapshot change with unsaved note preserved, 320/768/1440 visibility, 90 physical DOM row transitions.
- `tests/reconnect-policy.test.mjs` covers 5→60s bounded backoff, manual recheck, and no POST replay function.
- Dedicated CI browser job installs the pinned optional Playwright test dependency; core desktop runtime stays stdlib Python/SQLite. Failure screenshots and synthetic timing artifacts available for 3 days, no supplier/PNR/credentials.
- **Gaps:** real Windows Chrome and Edge, NVDA/screen reader, native 200–400% zoom, 8-hour heap/leak study and gold BA observation. These remain human UAT, not claimed complete.
- **UI redundancy:** `docs/UX_REDUNDANCY_SIMPLIFICATION_AUDIT.md` provides 16 source-backed candidates and grouped #35–#38 acceptance. No removals in v2.34.

## v2.35: visually quiet first-screen coverage

`tests/visual-clarity.test.mjs` verifies scan-only queue summary, all retained secondary counts, nonduplicated snapshot timestamp, Jira/manual/sprint provenance separation, blocking/WAIT/WRITE warnings, omission of neutral false signals and no repeated empty briefing. Existing Chromium browser E2E covers keyboard/CAS/modal/responsive and unchanged API. Real human time-to-action and screen-reader comprehension before/after remain OPEN: capture five BA archetypes and ensure warnings remain visible without scrolling.

## v2.36: clarity of copy vs approve and email actions

`tests/handoff-ui-policy.test.mjs` verifies exactly one enabled copy for structurally verified Jira drafts, explicit unverified/blocked manual rework fallback in detail, independent local approval and mail copy/open/batch labels without false sent status. Existing Chromium DOM E2E still covers the original controls. Human BA checks: false-ready=0 for unverified cases, approvals remain explicit, original description/supplier evidence remains available.

## v2.37: progressive disclosure preserved semantics

New `tests/progressive-layout.test.mjs` covers active nondefault filter marker, evidence count and canonical rank/filter invariants. The existing Playwright Chromium runner now tests the actual collapsed filter opened via summary, WRITE/outside sprint result counts, all Data menu actions after grouping, visible source and historical detail elements. Missing: human Windows 400% zoom, NVDA disclosures and deep-case fact/ZIP comparison.

## v2.38: CSS scope and responsive screenshot evidence

`tests/css-cleanup.test.mjs` detects removed obsolete strip/style helpers while preserving current provenance/focus/advanced filters. Playwright synthetic Chromium E2E now records full-page screenshots at 320/768/1440, asserts usable task queue and detail and no document overflow beyond 2px rounding. This is a **synthetic browser smoke**, not Windows Edge/native 400% zoom or pixel-approved baseline. See `docs/CSS_VISUAL_REGRESSION.md` and post-38 `docs/BACKLOG_CLOSEOUT_PLAN.md` for real acceptance.

## v2.39: backlog evidence integrity and explicit human UAT

`tests/test_backlog_audit.py` freezes the 129-row canonical inventory, verifies unique/prioritized rows, required acceptance criteria, missing evidence pointers, deferred cloud scope, route ownership, potential duplicate acceptance and cannot-auto-DONE gates. The CI `backlog_audit.py --check` regenerates the JSON and rejects manual/stale ledger changes. No actual Windows, Jira, Kibana, CCON or 20–30 gold-case acceptance was performed. See `docs/BACKLOG_RECONCILIATION.md` and `docs/BA_GOLD_CASE_ACCEPTANCE.md`.

## v2.40: cross-layer identity and local source freshness

`tests/test_value_mapping.py`: conflicting explicit IDs, one supplier used twice, multiple supplier retry IDs, incomplete exchanges, partial unique matching; no sensitive values/trace ID in outputs. `tests/test_evidence_provenance_40.py`: deterministic local source verification version and non-HTTP Kibana action-planning boundaries. Live Jira/Confluence source meaning and supplier API transformation remain outside synthetic CI.

## v2.41: manual supplier handoff readiness

`tests/test_email_rules.py` verifies that legacy attachment wording is stripped without explicit archive proof and that verified normalization stays idempotent. `tests/test_ba_output_checks.py` blocks affirmative attachment language when archive readiness is unknown. `tests/test_log_attachments.py` verifies single valid ZIP plus missing second flow returns PARTIAL, preventing falsely ready email copy. Real recipient and Outlook composer human UAT remains open.

## v2.42: undo safety and real browser focus

`tests/manual-done-undo.test.mjs`: token validation, wrong issue, stale revision, inactive task, once-only DONE undo; payload sends exact expectedManualRevision and status only, never Jira/email. `browser_e2e.py`: actual Chromium Done confirmation → successful SQLite save → click undo → original manual status restored. Real Windows keyboard/time-to-action and human semantic approval remain open.

## v2.43: priority invariants and opt-in recipient

`tests/priority-hard-lanes.test.mjs`: active sprint vs backlog across score range; WRITE > READY same lane; manual DONE under open backlog; unverified not promoted; quick effort hints do not mutate sorting. `browser_e2e.py`: synthetic AF/KL-like task shows empty recipient until explicitly using template; deleting it and Save/Reload retains blank. No supplier address validity is proven, and actual live BA UAT is still required.

## v2.44: RCA contrast candidate safety

`tests/test_error_series.py` verifies distinct same-issue/supplier contrast candidates are deduplicated and bounded, absent-code candidates cannot inflate affected-case prevalence, missing contrast is a visible gap, and no-root-cause-proof labels survive. Corporate supplier success remains outside synthetic CI.

## v2.45: local backup clock validation

`tests/test_local_backup.py`: filename/UTC metadata consistency, forged future or timezone-free manifest rejection, and clock-rollback eligibility; existing offline restore/repair/corrupt WAL/SQLite tests remain. Real Windows Task Scheduler, file locks, BitLocker and forced-power-loss testing are not covered by Linux CI.

## v2.46: actual DOM large synthetic queue

`browser_e2e.py` covers 100, 500 and 1000 in-memory synthetic Jira tasks via real Chromium cold reload, filter transition and p50/max observed search latency. It writes sanitized aggregate timing artifact. `tests/task_rules.test.mjs` guards punctuation-only and mixed clean-token false positives. No claims about Windows hardware, 8-hour uptime, long private real descriptions or screen-reader success.

## v2.47: accessible queue semantics and forced-color emulator

`browser_e2e.py` asserts heading roles/levels, manual email CTA visibility, keyboard focus outline and 320px no-global-horizontal-overflow with forced-colors/reduced-motion emulation. Actual native 200–400% zoom, Windows/Edge/NVDA and human-comprehension UAT are separate, not claimed complete. See `docs/A11Y_FINAL_SCOPE_REVIEW.md`.
