# CSS and visual regression cleanup, v2.38

## Source-audited deletions, not a redesign

The old task metadata row (`.task-badges`, `.signal-strip`, `.signal-text` and text-tone aliases) was replaced by provenance-labeled `.task-meta-compact` in #35. A grep across `dashboard.html` and `assets/dashboard.mjs` on v2.37 found **zero runtime uses** of the removed class names. PR #38 deletes only these orphan declarations (including legacy mobile overrides), not the original AERTiCKET brand, current signals, QA gate, email panel, task cards, fonts or grid.

The stylesheet had 1524 lines before this small cleanup. Some repeated selectors are **legitimate responsive overrides** under distinct media rules; deleting them by simple deduplication could break Windows 400% zoom or keyboard focus. We do **not** claim all CSS duplicates were safely consolidated.

## Browser verification

The opt-in Playwright synthetic Chromium suite now records screenshot artifacts at **320 / 768 / 1440 CSS px**, checks that `#detail` / queue remain visible and checks global horizontal overflow stays within 2px rounding. It also exercises keyboard/focus, CAS and recovery from previous releases. Screenshots contain **only synthetic test tasks**, retained temporarily in Actions; no production source/PNR/emails. CI geometry checks are useful regression indicators, **not pixel-perfect visual diffs** against an approved Windows screenshot baseline.

A human operator should compare old vs new Windows Chrome/Edge on the same device, DPI, zoom (100%, 200%, 400%), font availability, colors, task archetype (READY/WRITE/WAIT/BLOCKED/deep evidence) and confirm:
- same familiar left queue / right detail design, same scrolling and position restore
- no hidden Jira status vs manual state, blocker, stale/CAS error or unverified copy warning
- keyboard controls remain visible, and long REST/JSON/code content does not create unexpected page overflow
- native 400% zoom/320px, screen reader and Windows high contrast remain usable

## Why no complete CSS overhaul yet

Rewriting all ~1500 lines of responsive CSS in one PR would increase regression risk without production screenshots. #38 intentionally performs a small, verifiable dead-style cleanup and adds browser artifact evidence. Any further formatting/token/cascade consolidation should be done **after** the human visual UAT and can be incorporated into #47 if concrete defects are observed.

## Next backlog

See `docs/BACKLOG_CLOSEOUT_PLAN.md` for the whole 129-row inventory and recommended **10 additional scoped PR (#39–48)** for the local product, plus mandatory independent gold-case/Windows UAT. Deferred cloud P3 features are not implicitly accepted.
