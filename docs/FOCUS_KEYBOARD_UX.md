# v2.30: keyboard-first focus, interruption recovery and truthful save feedback

**Status:** merged only after synthetic tests and CI. Real Chrome/Edge/Windows/assistive technology UAT remains OPEN. Single-analyst local workflow; no new tabs, dashboard modes, Jira writes, supplier log transfers or automatic email sends.

## Task navigation in the existing screen

| Keyboard | When active | Action | Deliberate safety limit |
|---|---|---|---|
| `/` | Not typing in an input/editor and no modal | Focus/select queue search | Does not steal typed text or intercept `/` in REST/URL notes |
| `Alt+↓` | Not typing and no modal | Focus next task **in visible filtered sorted queue** | Wraps within current filter, no priority changes or auto-DONE |
| `Alt+↑` | Not typing and no modal | Focus previous task in visible queue | Same constraints |
| `Alt+C` | Not typing and no modal | Copy **current** next action via existing button | No Jira write, no copy of stale action, no email send |
| `Ctrl+Enter` or `Cmd+Enter` | Editing a detail field and no modal | Save local note/status/effort/email through existing CAS-backed form | Does not trigger Done, Outlook or Jira write |
| `Escape` | Existing menu / native modal behavior | Close menu or modal | Doesn't discard edits, no destructive shortcut |

**Keyboard discovery:** an ordinary collapsed `<details>` lives below queue filters and describes navigation. All key handlers are ignored while the bulk-mail modal is open; navigation and Copy are ignored in inputs, textareas, selects, contenteditable, aria-role textbox, IME composition, modifiers/repeats. Native buttons and selectors remain keyboard-operable. This is not a claim of full WCAG conformance.

## Non-destructive focus recovery

- The selected issue and view are scoped to **one browser tab** using sessionStorage (`ccon-ba-desk.view-context.v1`). Reload/revisit can return to the selected key and a bounded list of up to 12 remembered task views. If storage is denied or corrupt, the app works normally without persistence.
- For each task, only scroll position, hashed disclosure identities/open states and optional editor cursor coordinates are stored. **Never store raw Jira summaries/description, note/email text, supplier identifiers or source excerpts** in this view state. An opaque 32-bit UI disclosure hash is used for stable matching, **not** for cryptographic integrity/confidentiality. User content remains in the existing separate unsaved-form recovery mechanism.
- When the same detail is rerendered, restore expanded state by **hashed semantic heading** rather than array index (array order may shift when new QA/source sections appear). Preserve detail scroll; if an editor was active, restore focus and caret. When switching tasks, remember caret and section states but **do not auto-focus an old textarea**: keyboard navigation remains on the task row.
- List rerender captures and restores row focus by issue key, only if focus was already in the queue. It does not steal focus from a typed form, search field or modal. Navigation commands follow the existing `visibleTasks()` filter and authoritative `rankTasks()` sorting without mutating score, active sprint or WRITE.
- A live background revision arriving while **any element in the task detail has keyboard focus**, or while its form is dirty, does not destroy the DOM. Display the existing stale notice and postpone the rerender until focus leaves the detail, the user explicitly saves, or the form is discarded. This preserves links, copy controls and visible cursor during read.
- The batch mail `<dialog>` uses browser-native modal focus containment, initially focuses the safer **Close** button, and returns focus to the opening control on Close / Escape; it does not auto-send any messages.

## Save feedback: what the states actually prove

| Visible state | Trigger | Implication |
|---|---|---|
| `✓ Збережено` | Clean form with no failure and no CAS conflict | Stored local draft/status matches this view (subject to normal concurrent freshness) |
| `Є незбережені правки` | Textarea/select updated | Edits only in browser recovery, not yet acknowledged by server |
| `Зберігаю зміни…` | In-flight local save | Not yet confirmed; Save/Done disabled |
| `Не збережено: …` | HTTP/local failure | No success claim; unsaved fields persist; can retry |
| `Конфлікт версій. Правки не перезаписано.` | Concurrent tab's `manualRevision` differs | Review existing conflict UI, explicitly accept saved or overwrite with a new CAS token |
| Stale-analysis notice | New Jira snapshot while writing/reading | Context changed; existing typed text not destroyed, source correctness needs another review |

**No cloud telemetry** of timings, keyboard shortcuts, focus positions or unsaved data. The existing private local copy remains the single source of truth.

## Deterministic regressions

`tests/focus-navigation.test.mjs` checks modifier safety, composition, modal guard, text targets, filtered queue wrap, semantic section identity across reordered disclosures, unchanged textarea contents on caret restore, session state sanitization and invalid keys. Existing `tests/manual-edit-policy.test.mjs` / `tests/test_manual_edit_cas.py` enforce SQLite CAS and draft integrity. CI also checks JS syntax, Python/Node unit tests, offline packaging and Compose validation.

The test suite validates **pure policies and contracts**, not a real rendered browser. The source now has UI wiring and a native dialog. Full DOM E2E, live screen reader, keyboard OS conflicts and 200–400% zoom still need browser execution, not a fictional pass.

## BA acceptance checklist (human UAT still open)

1. On Windows Chrome/Edge, run at least 5 task archetypes, including real WRITE with an unsent draft and a deep multi-error task. Measure time-to-next-action, time-to-handoff and interruptions without exposing private source logs in CI.
2. Put cursor in middle of a note, use keyboard to leave and return; confirm text unchanged, caret position intact on refocus, detail section and scroll restored, and selected row still navigable.
3. Apply signal/sprint/search filters, navigate forward/back; **no filtered-out tasks, no reordered sprint priorities**, no unexpected Done or mailto.
4. While typing REST/PNR technical examples including `/` and modifier combinations, ensure shortcuts never steal keys. Test IME/Polish keyboard and input focus.
5. Simulate a 409 save conflict, stop local server while saving, restart, use browser's Back/Reload, and verify distinct Saved/Unsaved/Saving/Error states. Never claim Saved before HTTP acknowledgment.
6. Open batch-mail dialog via keyboard, close via Escape, return to the opener; no accidental external delivery and no priority change.
7. Run narrow screen, 200/400% zoom, screen reader and high contrast. Record blocking accessibility findings separately.

**Backlog follow-ups:** full browser E2E runner, keyboard shortcut customization/conflict UAT, pending-save retry design, screen reader and zoom tests, timed operator study, and two-tab local unsaved-form collision. A passing GitHub CI does not establish real-world ergonomics.
