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
