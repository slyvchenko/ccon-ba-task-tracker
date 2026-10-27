# CCON BA: історичний GitHub review audit (2026-10-27)

[Повний реєстр 148 inline findings](PR_REVIEW_COMMENT_REGISTER.json) має для кожного exact comment URL, PR, файл, пріоритет, thread ID, resolved/outdated стан, disposition та наступну дію. Усі URL стосуються публічного GitHub коду, без реальних Jira/PNR/XML/ZIP.

## Статус
- **90 PR** (merged/closed), **211 inline comments** (148 оригінальних та 63 відповіді).
- Додатково **206 загальних conversation comments**: 187 PR і 19 до Issue #50. Переважно рев'ю-підсумки, а не незалежні кодові finding; коментар власника до #83 підтверджує superseded PR #82.
- **148 threads аудовано: 78 Resolved, 70 Open**, усі відкриті P2, **P1 Open = 0**. З них 26 outdated, але це не автоматичний дозвіл їх закрити.
- За audit fixes **14 original comments** пов'язані з 7 новими merged PR; **17** підтверджено виправленими раніше, **1** WIP PR #71 superseded без merge.
- **70 open** позначені `SOURCE_LEVEL_TRIAGE_REQUIRED`, а не DONE. Їхні точні comment URL та file paths доступні в JSON для наступних source-level перевірок.

## Review fixes: усі 4/4 synthetic CI

| PR | Findings | Scope |
|---|---:|---|
| [#85](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/85) | 4 | Pointers, symlinks, SQLite journal, draft overflow |
| [#86](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/86) | 2 | Browser storage, clock rollback |
| [#87](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/87) | 1 | Cross-tab CAS on focused refresh |
| [#88](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/88) | 2 | UTF-16 DTD, XML namespace shapes |
| [#89](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/89) | 1 | QA-13 mandatory UAT routing |
| [#90](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/90) | 2 | Jira attachment parent links and report cap |
| [#91](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/91) | 2 | Symlink ancestors in diagnostics |

## Поточний залишок P2: концентрація за файлами

| Файл | Open comments |
|---|---:|
| `assets/dashboard.mjs` | 14 |
| `weekly_workload.py` | 8 |
| `ba_quality_gate.py` | 3 |
| `confluence_local.py` | 3 |
| `browser_e2e.py` | 3 |
| `local_error_budget.py` | 3 |
| `ba_output_checks.py` | 2 |
| `assets/visual-clarity.mjs` | 2 |
| `assets/dashboard.css` | 2 |
| `local_diagnostics.py` | 2 |
| `sqlite_mode_study.py` | 2 |
| `history_retention_preview.py` | 2 |
| `tests/test_backlog_audit.py` | 2 |
| `server.py` | 2 |

Порядок подальшої source-level перевірки: security/privacy та ризик втрати ручних правок, достовірність BA-доказів, UX із впливом на рішення, далі тести/документація. Outdated і дублікати спершу звіряються з `main`, а не механічно резолвляться. Кожен підтверджений дефект варто виправляти невеликим тестованим PR.

**Межа приймання:** canonical backlog залишається 129 (40 code-IMPLEMENTED / 82 PARTIAL / 3 human GATE / 4 DEFERRED), release `BLOCKED_INDEPENDENT_UAT`. [Issue #50](https://github.com/slyvchenko/ccon-ba-task-tracker/issues/50) лишається open, потрібні 26 незалежних BA-кейсів, live Jira/Kibana/CCON та native Windows/Edge/NVDA/crash/8h acceptance. CI не замінює human signoff, ніяких автоматичних Jira writes або деплою не робилось.
