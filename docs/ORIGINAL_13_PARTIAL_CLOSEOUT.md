# Вихідні 13 пунктів: завершення технічної підготовки та межі приймання

**Дата:** 27.10.2026. **Поточний код:** v2.50.9. **Це не означає виконане бізнес-приймання.** Всі наведені вимоги мають статус `PARTIAL`, не `IMPLEMENTED`/human-approved. 129 canonical IDs збережено.

| ID | Код / PR | Що ще потрібно |
|---|---|---|
| PERF-09 | PR #69: безпечна невелика консолідація CSS і regression contracts | Повна оцінка каскаду, approved Windows/Edge DPI/zoom screenshots та NVDA |
| PERF-10 | PR #61: synthetic SQLite WAL/index study | Емпіричний production-like trace на Windows та рішення, чи потрібен index/WAL |
| REL-09 | PR #61: read-only history retention preview | Retention policy, добровільне погодження, rollback/backup і real data audit |
| REL-10 | PR #65: source-only release hashes і fail-closed rollback advisory | Незалежний підпис, provenance, backward SQLite/Windows migration |
| PRIOR-05 | PR #62: explainable impact/urgency/effort/unblocking | Незалежне ранжування реальних задач із BA signoff |
| PRIOR-07 | PR #66: локальні handoff time aggregates | Вимір TTNA/TTSH на реальних BA сценаріях |
| PRIOR-08 | PR #66: добровільні manual priority corrections | Реальний correction review без автоматичного перенавчання |
| PRIOR-09 | PR #67: локальні read-only WIP/blockers/rework summaries | Багатотижнева перевірка операційної корисності |
| QUICK-08 | PR #63: placeholder-only candidates | Експертна оцінка 20–30 gold-case задач без вигаданих джерел |
| FOCUS-07 | PR #62: ручний pin у межах lane | Реальні keyboard/Windows/BA feedback |
| FOCUS-08 | PR #62: відновлення фокусу після дій | Windows default mail-client і NVDA UX |
| OPS-04 | PR #68: тільки opt-in local HTTP error budget | Не доведено повний availability SLO; реальна користь і native smoke |
| QA-13 | PR #70: локальний анонімний 20–30 case review preflight | **Фактичні незалежні еталони, оцінки, TTNA/TTSH і signed human acceptance** |

## Підсумок без підміни значень

- **13/13** початкових `PLANNED` вимог отримали часткові code/test рішення й тепер `PARTIAL`. Це **не** означає, що пройдено 13/13 критеріїв приймання.
- Стан 129 канонічних пунктів: **40 IMPLEMENTED (лише код), 82 PARTIAL, 0 PLANNED, 3 GATE, 4 DEFERRED**.
- `human_acceptance=NOT_RECORDED` для кожного пункту. Незалежний reviewer, авторизовані Jira/Kibana/CCON, 26 gold cases, Windows ACL/BitLocker/Edge/NVDA/8h і фізичне відновлення залишаються окремими gates у [Issue #50](https://github.com/slyvchenko/ccon-ba-task-tracker/issues/50).
- Жодного real source, email, REST/supplier ZIP, токена, cookies, PNR чи персональної інформації не потрапляє у CI з цих змін.

Використовуйте `docs/BA_GOLD_CASE_ACCEPTANCE.md`, `docs/PRIVATE_GOLD_REVIEW.md` і `docs/CSS_VISUAL_REGRESSION.md` для виконання залишкових дій. **Не позначайте DONE** лише через зелені синтетичні CI перевірки.
