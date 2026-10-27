# 13 запланованих покращень: технічний стан і незакрите приймання (v2.50.9)

У цьому пакеті **немає жодного залишку PLANNED** серед початкових 13 вимог. Але **всі 13 залишаються PARTIAL** до фактичного BA/Windows/UX приймання. `IMPLEMENTED (code)` у реєстрі не є людським схваленням.

| ID | Технічний результат | Що ще потрібно для повного приймання |
|---|---|---|
| PERF-09 | Прибрані дублікати CSS, статичні та Chromium перевірки | Візуальна регресія Windows/Edge/Chrome, zoom, keyboard/NVDA |
| PERF-10 | Синтетичні SQLite DELETE/WAL/index/backup виміри | Реальне Windows/SSD навантаження, рішення щодо індексів |
| REL-09 | Приватний read-only підрахунок застарілої історії | Retention policy, згода на архівування/видалення, restore |
| REL-10 | Верифікація SHA256 релізів та advisory rollback | Незалежний підпис, сумісність старої схеми на Windows |
| PRIOR-05 | Окремі impact/urgency/effort/unblocking | Експертний acceptance правильності ранжування |
| PRIOR-07 | Локальні TTNA/TTSH / час передачі по архетипах | Реальні виміри з незалежним baseline |
| PRIOR-08 | Ручна анонімізована корекція пріоритету | Валідація корисності без автоматичного retraining |
| PRIOR-09 | Тижневі WIP/blocker/rework агрегати | Багатотижневе BA спостереження |
| QUICK-08 | Шаблони з placeholders, без вигаданих правил | Gold-case перевірка шаблонів |
| FOCUS-07 | Локальний pin задачі без Jira priority write | User acceptance у реальній черзі |
| FOCUS-08 | Відновлення focus після Save/bulk/mailto | Native mail client і keyboard UAT |
| OPS-04 | Опціональний локальний HTTP error budget | Windows операційна перевірка, валідність показника |
| QA-13 | Приватний gold review preflight з перевірками безпечного scope | **20–30 реальних** незалежних BA gold кейсів, критичні errors=0, підпис людини |

Ні CI, ні synthesized corpus не мають права підвищувати ці статуси до `DONE`. Всі `human_acceptance` у `docs/BACKLOG_ACCEPTANCE_LEDGER.json` залишаються `NOT_RECORDED`; користувацькі Jira/PNR, supplier XML/REST/ZIP не повинні потрапляти в GitHub.

**Висновок:** розробка первинних механізмів для 13 вимог розпочата/реалізована настільки, щоб перейти до приймання, проте повне виконання беклогу **не сертифіковане**. Додаткові PARTIAL/GATE/DEFERRED за межами цих 13 теж лишаються.
