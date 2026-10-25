# Local-first performance, reliability and operations contract

**Status:** 2026-10-25. Targets below are acceptance hypotheses, not measured results. Python standard library + SQLite + browser ES modules, no production telemetry, no corporate sample logs.

## Architecture of the fast path

```text
Open http://localhost:8765
  -> GET /api/tasks (one current full snapshot)
  -> render queue + selected detail (preserve local drafts)
Every 5s, only while tab visible
  -> GET /api/tasks/revision (SQLite single integer + current import error)
     -> unchanged: no full JSON, no task parsing, no full list repaint
     -> changed or unseen: GET /api/tasks, redraw only if payload changed
Every 15s visible: refresh selected logs
Every 30s visible: refresh daily report and optional cloud health
Background tab: suppress periodic fetch; on foreground: immediately check revision
Save manual state -> one SQLite transaction + monotonically increment revision
Import new complete snapshot -> one SQLite transaction + monotonically increment revision
Duplicate/older/invalid import -> NO revision bump; existing state preserved
```

**Version is a change notification, not a consistency lock:** `state_revision` is transactional and monotonic for the application's built-in import and save paths. Other external/manual SQLite writers do not participate. GET /api/tasks and revision may race with later writes; next poll reconciles. The frontend still safeguards locally typed edits and ignores stale parallel load completions. True multi-client `If-Match`/optimistic CAS is a separate P0 backlog item.

## Why this matters

Previous browser behavior requested `/api/tasks` with all serialized Jira analyses **every five seconds**, plus logs, daily report and health with the same cadence. Full `Desk.view()` decodes every stored task snapshot from SQLite and the client stringifies the returned JSON even on unchanged data. With 100–1000 complex tasks, this is avoidable repeat work. This PR introduces a cheap constant-size revision response; full data is still loaded on initial open and after a material change.

Search had a similar unnecessary hot path: each no-query filter rebuilt a long search text from every task's full technical description/rules. The new filter checks active/done/sprint/signal first, and constructs technical text only when there is a real query. Later optimization (debounced indexing / virtualized rows) requires real browser measurement and accessibility validation.

## Reliability & data safety

- SQLite revisions and snapshot writes are in the **same transaction**; a failing write must not increment revision or publish partial state.
- Never alter or overwrite a user-edited note/email solely because the synced Jira fingerprint changed. Existing draft recovery must remain active.
- `GET /api/tasks/revision` is not a secrets or logging endpoint; it exposes only integer version and local import-error string under existing localhost host / cloud auth checks.
- Never rely solely on `revision` for source correctness, external Jira freshness, supplier ZIP readiness or semantic QA proof.
- `/api/export` and `/api/tasks` stay supported for offline recovery and manual export.
- The watcher detects valid new snapshot files; corrupt/newer invalid JSON reports error without corrupting prior DB.
- Avoid background polling when the page is hidden. When the tab regains focus, check the revision immediately; a failed server call gives an actionable error.
- Competing tabs can still overwrite a manually saved note. This needs per-task revision CAS, explicit conflict UI, and tests before claiming multi-tab safety.
- `data/`, `downloads/`, `ba_state.db` may contain corporate personal data. Enforce OS permissions and encryption; never attach them to public CI/PR or external analytics.
- The no-extra-package installation policy remains for the core application.

## Benchmark instructions

Use synthetic, **unclassified** fake tasks only. For each cohort size (100, 500, 1000) measure cold open and warm reload, `/api/tasks/revision`, `/api/tasks`, search first-key/last-key, selection, Save, Done→Next. Record laptop model, CPU, Windows build, browser version, power mode, number of tests, median and p95, memory and payload bytes. Benchmark both immediately after Windows reboot and during routine workload. Prefer the same machine and same synthetic fixture before/after; no ungrounded comparison of times from different machines.

A Python-only local latency/response-size diagnostic is available:

```powershell
python performance_smoke.py --sizes 100 500 1000 --iterations 25
```

It uses temporary generated fake SQLite tasks, does not call Jira, does not touch `ba_state.db` in your active repository, and reports p50/p95 of `Desk.view` vs `Desk.revision`. **It does not measure** real browser DOM, Windows startup, Confluence, Jira latency, AI inference, CPU power management or human action time. Do not compare performance across machines as a release proof.

### Provisional SLO and failure budget (validate in real UAT)

| Path | Candidate budget | Failure/diagnostic handling |
|---|---|---|
| GET revision, 1000 synthetic tasks | p95 <= 40 ms local laptop | performance regression investigation, do not fail CI based on shared runner wallclock |
| Initial 1000-task load in browser | p95 <= 2 seconds to interactive | measure real Chrome/Edge on Windows |
| Search input to results (1000 items) | p95 <= 100 ms after input | benchmark with technical-rich synthetic fixtures |
| Single manual save acknowledged | p95 <= 300 ms | status saved only after HTTP 200, no optimistic false success |
| Foreground resume / changed snapshot | p95 <= 2 s | refresh immediately upon visibility event |
| Backup / restart restoration | 100% previously acknowledged edits | forced stop/restart, partial JSON, multi-tab tests |
| Long-running 8h session | no UI-freezing growth, no lost forms | browser memory and event-listener leak audit |
| Quality or proof | 0 silent false-ready transitions | human BA review + gate regressions |

**CI strategy:** deterministic invariant checks for revision bumps, unchanged-state polling, invalid import, restart persistence, null/empty data, concurrent saves, search parity and demo 250-task payload reduction. Wallclock figures are logged in manual report, **never asserted as tight CI numbers**, because shared runners vary.

## Performance profiling plan for next PRs

1. **Frontend**: Chrome Performance/Lighthouse traces of cold 100/500/1000, input responsiveness, scripting/paint breakdown, rerender counts. Evaluate event delegation and visible-row/windowing only if measured bottleneck, preserving aria/keyboard.
2. **Backend**: profile `Desk.view`, `context`, repeated JSON serialization, SQLite locked writes under concurrent threads, JSON report parsing; add cache by committed revision only after correctness tests.
3. **Networking**: compare 5s full-payload baseline with 5s constant-size revision. Bound selected-log and report refresh and avoid duplicate in-flight loads.
4. **Reliability**: backup state, crash recovery, Windows lock contention, clipboard/mailto/browser failure, multi-tab CAS, source-staleness false-green warnings.
5. **Security**: loopback-only bind, host/origin checks, no external beacons, CSP, gitignore, no sensitive trace logging. Perform tests on approved sandbox only.

## Rollback & UAT

The implementation adds a `state_revision` table transparently on normal `Desk` startup and preserves all existing tasks and notes. If a regression occurs, stop the server, backup `ba_state.db` (no public upload), return to previously validated release; extra table is additive and older release should ignore it. Do not delete DB to "fix" a migration.

Before deploying to the daily local task, perform: cold start → synthetic import → one status change → edited mail save → `Done → Next` → browser reload → duplicate import → new import → temporary server stop → restart; inspect both branches' system output. Real Jira/Confluence/Kibana must be tested separately using the authorized workstation.
