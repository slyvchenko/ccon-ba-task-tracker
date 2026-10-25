# CCON BA Desk: оптимальний шлях закриття backlog після UI PR #35–38

**Оцінка станом на 25.10.2026**, після кодового аудиту v2.34–v2.37. Це дорожня карта, не гарантована кількість роботи й не підтвердження фактичної бізнес-готовності.

## Скільки задач реально відкрито

| Вимір | Пунктів | Тлумачення |
|---|---:|---|
| **Основний backlog** | **129** | CORE/BA/EVD/OUT/UX/QA/INF/QUICK/FOCUS/PRIOR/UI/PERF/REL/OPS/SEC/**A11Y**. Попередній підрахунок «123» не включав частину accessibility items |
| Позначено IMPLEMENTED | 37 | Стан у Markdown може відставати від фактичної реалізації: статус оновлюється вручну, деякі функції вже мають CI |
| PARTIAL | 52 | Значна частина має готову інфраструктуру і тестовий код, але не пройшла реальні BA/Jira/Windows UAT |
| GATE / PLANNED / NEXT | 36 | **3** acceptance gates із реальними кейсами + **32** planned + **1** next |
| DEFERRED | 4 | Cloud/SSO/PostgreSQL/multi-tenant/secrets P3, **не входять** до локального релізу |
| **VIS hypotheses** | **16 окремо** | Не є ще 16 незалежними features. Згруповані в #35–38: головний екран, handoff/CTA, progressive disclosures, CSS parity |

**Немає підстав автоматично перетворювати 92 формально не закриті рядки на 92 PR.** Більшість є acceptance criteria, косметичні гіпотези або функції, які вже частково існують. Рішення про додаткові зміни приймати після реального UAT на 20–30 задачах.

## Оптимальна оцінка після #38

<summary>

- **Цільовий план для стабільного локального продукту: 10 додаткових тематичних PR**, умовно **#39–48**. Діапазон **8–12**, якщо реальні gold cases змінять пріоритети; не обіцянка закрити всі P2/P3.
- **2–3 окремі етапи людського UAT** (live Jira/Kibana/CCON; real BA case reviews/Windows recovery; acceptance signoff). Їх **не можна замінити PR або CI**; доступ до приватного постачальника та рішення BA потрібні від власника.
- **Ще приблизно 3–5 PR**, лише якщо додатково обрано відкладений **хмарний продукт** з OIDC/SSO/HTTPS, БД PostgreSQL, hosting/backups/ops і security/legal approval. Він не є необхідною частиною локального BA Desk.
- **Абсолютно весь backlog «як написано», включно з cloud/P2 побажаннями:** не варто обіцяти остаточне число до scope decision та gold-set UAT. Орієнтир **13–17 PR після #38**, якщо не видаляти жодної опції.

</summary>

## 10 рекомендованих згрупованих PR для локального завершення

| PR | Зміст і об'єднані рядки | Вихід / обов'язковий gate |
|---|---|---|
| **#39, P0** | Reconcile backlog: визначити справжні DONE/PARTIAL, прибрати дублікати/надлишки, фіксована BA task-archetype матриця, single acceptance ledger; QA-02/03/10/13 як UAT gates | Відновлювані перевірки, 0 зміни бізнес-логіки без доказів; людина підтверджує реальні кейси |
| **#40, P0** | Evidence provenance: EVD-03/06/13, BA-09, OUT-04, QA-08. Синхронізувати мапінг REST→supplier→REST і evidence/ZIP/PDF доступність | Доказ із точними request/response IDs, заборона invented values; private Jira/Kibana UAT |
| **#41, P0** | BA handoff integrity: BA-01/02/05, OUT-01/02, QUICK-02/03/04; коректні Jira description/email/recipient/ZIP checks | QA-gated draft, false-ready=0, manual send/approval only |
| **#42, P1** | Робочий цикл: QUICK-05/06/07/08, FOCUS-04/05/07/08 (пакет, reversibility, sticky action, long-focus) | 5 task journeys, undo without external Jira actions, same-page UI |
| **#43, P1** | Пріоритети й метрики: CORE-10, PRIOR-01..09, OPS-01, QA-10 | Sprint/WRITE hard invariants untouched; time-to-handoff measured, no unverified effort SLA |
| **#44, P1** | Supplier RCA/taxonomy: EVD-10/14/15, QA-04/05/07; source scope/retention and cross-case correlation | QA gold-set, controlled retention, reproducible supplier test cases |
| **#45, P1** | Reliability/security: REL-02/03/04/05/06/07/08/09/10 + SEC-01/02/03/04, OPS-02/03/05 | Windows crash restore, private data ACL/BitLocker, strict CAS, no unsafe logs in public CI |
| **#46, P1** | Browser/perf/8h: PERF-05/07/08/10, QA-09/11/12/14/15 | 100/500/1000 synth & actual Windows/Edge profiles, 8h stability UAT |
| **#47, P1** | Last UX/a11y correctness: UX-02/03, UI-05/06/07/08/09/10, remaining FOCUS and A11Y | 320px/200–400% zoom, NVDA, no hidden danger/CTA, 20–30 case scan-time |
| **#48, P0 gate** | Release readiness: shrink unresolved backlog to clearly accepted/deferred rows, rollback/drill/runbook, BA signoff on real task corpus, deployment to Windows via deliberate local installer update | Publish **actual verified** state and coverage. If human acceptance absent, status must remain OPEN |

**Dependencies:** #39 acceptance inventory before claiming any rows closed; #40 and #41 before human source gold-set; #45 before hard-crash drill; #46–47 before final #48. Small independent improvements can be grouped, but not at the cost of readable PR review, source truth or business regressions.

## Що варто відкласти, а не механічно «виконати»

- **INF-01..04 P3:** cloud/OIDC/Postgres/SSO, поза ціллю локального інструмента одного BA. Реалізувати лише за окремим product decision, не для красивого «100% DONE».
- **Низька цінність без реального usage proof:** OPS-04 (повний dashboard error budget), EVD-14 (масова cross-case anomaly), PRIOR-09 (WIP dashboard), QUICK-08 (extra templates). Залишити **P2/experiment**, не копіювати на головний екран.
- **VIS-01..16:** зберегти рішення #35–38, не заводити другий UI backlog із тими ж дублями. Всі дії з окремими business semantics лишаються окремими.
- **UAT-блокери:** live Jira/Kibana/CCON auth, 20–30 gold-case semantic acceptance, Windows/NVDA/8h не можна позначати DONE з synthetic CI; тут PR не є заміною доступу та спостереження.

## Критерій справжнього «фіналу»

- Один знайомий dashboard; 3–5 секунд до чіткої наступної дії на простих задачах, якісний глибокий RCA без втрати proof на складних.
- Ні false-ready draft, ні outbound email/Jira write без людини, ні тихий overwrite notes/drafts або нестандартне підвищення backlog XS задач у sprint.
- Python/Node/release/Compose, Chromium synthetic E2E і фактичні BA/Windows/Edge/NVDA UAT мають незалежні evidence entries.
- Кожен відкритий рядок отримує явний стан **DONE (with evidence) / BLOCKED by real UAT / DEFERRED with rationale / DROPPED as redundant**; не перетворювати PARTIAL на DONE тільки для красивого проценту.
- Product Owner окремо затверджує, чи всі P2/P3 optional фічі взагалі входять у цільовий локальний продукт.

**Висновок:** **10 тематичних PR після #38** є найрозумнішою робочою оцінкою для локального BA Desk, якщо згрупувати пов'язані рядки і не додавати функції заради кількості. Реальна оцінка може зменшитися після #39 або зрости через проблеми, виявлені на реальних даних.
