# Другий аудит існуючих code/test locators (P1/P2)

Після P0 та першого P1-аудиту зіставлено ще **12** вимог із наявними source/test файлами. Нижче зафіксовано лише навігаційні прив'язки, а не підтвердження DoD.

| ID | Код | Синтетичний тест | Обмеження |
|---|---|---|---|
| CORE-08 | `ba_actions.py` | `tests/test_action_history.py` | Локальні плани, не факт реального виконання |
| CORE-09 | `assets/queue-performance.mjs` | `tests/queue-performance.test.mjs` | Детермінований пошук на synthetic, не Windows SLA |
| CORE-10 | `priority_consistency.py` | `tests/test_priority_consistency.py` | Сигнал дрейфу оцінки, не підтверджена якість ранжування |
| BA-11 | `approved_draft.py` | `tests/test_approved_draft.py` | Локально погоджений reference, не зовнішнє Jira схвалення |
| EVD-09 | `value_mapping.py` | `tests/test_value_mapping.py` | Перевірка структури порівняння значень, не live контракт supplier |
| EVD-14 | `evidence_trends.py` | `tests/test_evidence_trends.py` | Явні timestamp та дублікати, без реальної інцидентної статистики |
| UX-03 | `assets/dashboard.css` | `tests/css-cleanup.test.mjs` | Стилі та контракт кольорів, не незалежне бренд-схвалення |
| UX-04 | `assets/dashboard.mjs` | `browser_e2e.py` | Synthetic quick UI, не реальний шлях із mailto |
| QA-07 | `supplier_logs.py` | `tests/test_evidence_regression_matrix.py` | Синтетичні malformed XML/multi-error сценарії, не live supplier |
| PERF-07 | `performance_smoke.py` | `tests/test_local_performance.py` | Синтетичний benchmark, не 8-годинний Windows soak |
| A11Y-05 | `assets/dashboard.css` | `tests/css-cleanup.test.mjs` | Наявність forced colors/reduced motion CSS, не NVDA/Windows перевірка |
| SEC-04 | `assets/draft-recovery.mjs` | `tests/draft-recovery.test.mjs` | Локальне збереження чернетки, не Windows ACL/encryption review |

**Результат:** прямі code+test locators **94 → 106**, вимоги без прямого code locator **29 → 17**. Категорії всіх 129 вимог незмінні: 40 `IMPLEMENTED` за кодом, 82 `PARTIAL`, 3 `GATE`, 4 `DEFERRED`, 0 `PLANNED`. Людське приймання для **кожного** пункту: `NOT_RECORDED`.

Без доказів залишаються, зокрема, `QA-02/QA-10` (приватні людські гейти), `EVD-05` (авторизований доступ до ZIP), `INF-01..04` (свідомо відкладений cloud scope), а також декілька довгих Windows/UX-сценаріїв. Не призначати їм випадкові source pointers. Жодної корпоративної задачі, PNR, XML, email або приватного шляху до цієї документації не переноситься.
