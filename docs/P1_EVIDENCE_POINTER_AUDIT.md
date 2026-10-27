# P1: 16 перевірених прив'язок до існуючого коду та синтетичних тестів

**Обсяг:** виключно аудит коду та тестових файлів після v2.50.12, без функціональних змін, перемикання режимів, мережі або корпоративних даних.

| Вимога | Існуючий код | Синтетичний тест | Межа доказу |
|---|---|---|---|
| CORE-07 | `task_history.py` | `tests/test_action_history.py` | Локальна ревізійна історія, не реальна переписка |
| BA-06 | `question_candidates.py` | `tests/test_question_decisions.py` | Лише можливий новий коментар, не підтверджена відповідь |
| BA-08 | `one_task_review.py` | `tests/test_one_task_review.py` | Один target, не продакшн-модель |
| BA-10 | `ba_decisions.py` | `tests/test_question_decisions.py` | Human-confirmed lifecycle, не бізнес-підпис |
| EVD-10 | `evidence_health.py` | `tests/test_evidence_health.py` | Підказки категорій помилок, не перевірка реальних версій supplier |
| EVD-11 | `flow_diagnostics.py` | `tests/test_flow_diagnostics.py` | Часова послідовність лише за явними timestamp |
| EVD-12 | `evidence_health.py` | `tests/test_evidence_health.py` | Синтетичні категорії доказовості |
| QA-04 | `ba_quality_gate.py` | `tests/test_ba_quality_gate.py` | Структурний QA, не фактичний gold-review |
| QA-05 | `prompt_calibration.py` | `tests/test_prompt_calibration.py` | Локальний feedback checklist; production prompt без auto-write |
| QA-06 | `prompt_experiments.py` | `tests/test_prompt_experiments.py` | Тест staging A/B і fail-closed approval, не реальний gold-set |
| FOCUS-03 | `assets/focus-navigation.mjs` | `tests/focus-navigation.test.mjs` | Keyboard logic без реального NVDA |
| PRIOR-04 | `assets/effort-planning.mjs` | `tests/effort-planning.test.mjs` | Евристика з низькою впевненістю, не доказ продуктивності |
| UI-06 | `assets/manual-edit-policy.mjs` | `tests/manual-edit-policy.test.mjs` | CAS та захист від stale edits, без реального UX-приймання |
| PERF-04 | `assets/queue-performance.mjs` | `tests/queue-performance.test.mjs` | Детермінований пошук, не Windows p95 SLA |
| PERF-06 | `desk_store.py` | `tests/test_json_response_cache.py` | Atomic revision/cache, не hardware crash guarantee |
| A11Y-01 | `assets/focus-navigation.mjs` | `tests/focus-navigation.test.mjs` | Синтетичні keyboard shortcuts, не повний assistive-tech UAT |

**Точна зміна обліку:** `code_plus_test_locators` 78 → **94**; `no_direct_locator` 45 → **29**. Усі 129 статусів залишаються попередніми: 40 `IMPLEMENTED` лише за кодом, 82 `PARTIAL`, 3 `GATE`, 4 `DEFERRED`. `human_acceptance=NOT_RECORDED` для кожного рядка. `PLANNED=0` не означає release-ready.

**Свідомо не мапили** `EVD-05` (авторизоване ZIP acquisition) та публічні `QA-02` / `QA-10` як докази реалізації. Вони потребують реальних приватних дозволів, браузерних спостережень і незалежного підпису. Решту невказаних P1/P2 не слід автоматично вважати відсутніми.

Джерело: `docs/PRODUCT_BACKLOG.md`; автоматичний відбиток `docs/BACKLOG_ACCEPTANCE_LEDGER.json`; генератор `backlog_audit.py`. Source/test locator є **місцем для перевірки**, а не результатом її виконання.
