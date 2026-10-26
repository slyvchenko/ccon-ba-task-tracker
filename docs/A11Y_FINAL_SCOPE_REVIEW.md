# v2.47: a11y and lean-UI implementation boundary

This is a **source and synthetic-Chromium implementation review**, not an NVDA, Windows Chrome/Edge, 200/400% native zoom, 20–30 real-case usability or WCAG conformance certification.

## Changes in #47

- Queue group separators are exposed as actual semantic headings (`role=heading, aria-level=3`) to assistive technology while preserving the familiar left queue/right detail page, sorting, keyboard navigation, and visual appearance. None of the Jira statuses or supplier evidence gets deleted.
- The `S?` hint is explicitly marked as an approximate unverified quick task, **not** a queue re-ranking or accepted time estimate, and is readable without hover-only `title`.
- Synthetic Chromium checks group semantics, one set of primary manual email controls, visible focus outline, 320px overflow in forced-colors and reduced-motion modes. This exercises browser CSS emulation, **not** actual Windows high-contrast, Edge, accessibility APIs or screen reader narration.

## Optional/deferred product scope

The 16 VIS hypotheses were grouped across #35–38; none is a new mandatory second dashboard. The remaining QUICK-08 templates, FOCUS-07 pinning, OPS-04 telemetry dashboards, PRIOR-09 WIP dashboards and further CSS rewrites are **OPTIONAL UAT CANDIDATES** rather than automatically worth their clutter and maintenance burden. Keep existing features and exact source data intact until human evidence supports removal.

The product must retain source provenance, technical contract rules, quality-gate failures, risk warnings, manual Jira/email handoff, current local status vs Jira state, per-task revision conflicts and recovery. Do not hide or transform these just to reduce element count.

## Acceptance remaining open

- Windows Chrome and Edge: native 100/200/400% zoom, 320px viewport, keyboard focus sequence, screen reader with NVDA, OS forced-color and reduced-motion.
- At least 20–30 source-verified real BA task archetypes, including ERROR/WAIT/WRITE/READY, multi-city deep error investigation, status conflict, pending ZIP and stale Jira context.
- Compare prior vs current time-to-next-action, action accuracy, missing critical conditions, focus loss, wrong recipient and false-ready rate. **No performance gain or WCAG AA compliance is claimed** without those external acceptance results.
