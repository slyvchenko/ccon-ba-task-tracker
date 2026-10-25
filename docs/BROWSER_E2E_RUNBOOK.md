# Browser E2E v2.34: Chromium evidence and Windows UAT boundary

## What CI actually runs

The `browser-e2e` job separately installs `playwright==1.56.0` and Chromium on Ubuntu, then executes `python browser_e2e.py`. The normal user's Python/SQLite-only application has no Playwright runtime dependency; ordinary checks still run `python check_project.py`. This is **actual DOM/browser interaction**, not just JS pure-function tests.

A self-contained fixture creates three **fully synthetic** tasks in a temporary SQLite database and starts `ThreadingHTTPServer(handler(Desk))` on 127.0.0.1 with an OS-assigned port. No Jira credentials, PNR, production log ZIP or real email addresses are loaded. The tests cover:
- Confirmed active sprint/WRITE ordering, keyboard Alt+Down, local note Save/CAS.
- Two real independent browser tabs editing the **same** issue: reload retains both unsaved drafts, first Save succeeds and second must receive conflict/409 without losing own text.
- Batch email preview dialog: initial safe Close focus, Escape and return focus. `open-batch` is never triggered.
- Abort read-only revision request to simulate disconnection. Dirty note survives; upon return of GET, the recovered status appears and no accidental POST occurs.
- Update/import a newer synthetic snapshot during a dirty form, preserving current unsaved text.
- Responsive visibility at 320, 768, 1440 CSS pixels. A short synthetic soak of 90 actual clicks records median/maximum measured click latency.

Failures and synthetic timing JSON are uploaded to GitHub Actions as a **3-day** artifact. Do not use these Linux timings as Windows SLO or proof of 8-hour stability.

## Local repeat

```bash
python -m pip install playwright==1.56.0
python -m playwright install chromium
python browser_e2e.py
```

Use a dedicated virtual environment. If your organization does not permit downloading browsers/dependencies, ask the owner to run these tests in an approved isolated CI runner. **Do not point the tests at the real production BA Desk.**

## Additional Windows acceptance, not performed by CI

1. Chrome/Edge 320 CSS px, 200%/400% actual zoom, screen reader NVDA and Windows forced colors, focus visible and all primary actions reachable.
2. Duplicate Tab / cloned sessionStorage, two tabs saving distinct notes, stale 409 and manual conflict resolution with real browser behavior.
3. Eight hours with 100/500/1000 synthetic tasks under the real Windows scheduled launcher: cold load, 5-second polling, suspended background tabs, heap snapshots, reconnect after sleep, refreshes, caret and scrolling. Report p50/p95/p99 and any growth.
4. Five real BA task archetypes only in a **private** environment, with human approval for exact Jira supplier descriptions and availability. Verify no external email send / Jira write, no missing ZIP, and no false safety claims.
5. Verify the proposed visual simplification backlog `docs/UX_REDUNDANCY_SIMPLIFICATION_AUDIT.md` before any feature removal. Count competing CTAs, scrolls and duplicated phrases; distinguish differently purposed actions.

## Safe reconnect contract

Only `GET /api/tasks/revision` and necessary `GET /api/tasks` are retried. After failures, delay grows 5s→10s→20s→40s→60s cap. Browser online / foreground actions may force a read. Do not retry manual `POST` (Save, DONE, email) without the user explicitly acting again. Offline message is shown once and cleared on confirmed GET recovery; dirty form remains in tab until acknowledged by SQLite.

**Known caveats:** synthetic Chromium tests cannot validate real Outlook opening on Windows, NVDA announcements, native browser zoom or an 8h OS soak. Evidence is CI build-specific; measurements are not BA business-quality approval.
