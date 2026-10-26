# PR #56: keyed queue patch and compact next-action scroll aid

## Why
A 500–1000-task queue already has cached sorting/search, but `renderList()` used to replace **all** visible buttons even when only one task's summary, status or badge changed. This causes avoidable DOM work and can disturb focused keyboard rows. The existing detailed panel also requires scrolling back up to copy the next action.

## Implemented, no new screen
- A small `queue-dom.mjs` reconciler compares **ordered group and task node IDs**. If their structure and order stay fixed, it replaces only changed HTML nodes. If filter, rank, group or length changes, it performs a safe full rebuild instead of trying to patch mismatched rows.
- All real task buttons remain in DOM, including 1000-task lists. No virtual rows or altered keyboard/tab/ARIA order. Existing `#list` click delegation, focus restoration and scroll preservation stay intact.
- One compact sticky **next action** appears only after the existing quick-handoff panel scrolls above the viewport. It shows a single-line preview and a copy-only button, using the existing next-action policy. Its zero-height slot does not shift the editor/scroll and it does not send email or write Jira. The original full quick-handoff remains the only canonical editable/reading location.
- The existing responsive detail layout and primary next-action block remain unchanged. The bar is not a new user mode.

## Automated tests
- Node: 100, 500, 1000 task node-diff invariants, unchanged rows vs one changed row, rank/order/structure/group fallbacks.
- Chromium: **500 rows**, selected keyboard-focused row retains DOM identity and focus when an unrelated row changes; changed row is replaced and count remains 500. Sticky action shown/hidden on detail scroll without a new tab.
- Linux Python/Node/release and Windows unit smoke; source import must be registered in server static allowlist and release manifest.
- Manual Windows/Edge/NVDA/320px accessibility and actual-device p50/p95 still need approval in Issue #50.

## Backlog status
- `FOCUS-05`: PLANNED → PARTIAL (implemented DOM/CSS behavior, real responsive user acceptance not recorded).
- `PERF-05`: remains PARTIAL (keyed updates and synthetic browser regression; 500/1000 live device performance not verified).
- 129 total: **40 IMPLEMENTED, 65 PARTIAL, 17 PLANNED, 3 GATE, 4 DEFERRED**. All 129 still `human_acceptance=NOT_RECORDED`.
