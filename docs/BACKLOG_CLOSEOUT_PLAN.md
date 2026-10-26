# CCON BA Desk: оптимальний шлях закриття backlog після UI PR #35–38

**Актуалізовано 26.10.2026 для PR #39.** Кількості й формальні статуси зафіксовано машинним аудитом після v2.38; бізнес-готовність не доведено. Це дорожня карта, не гарантована кількість роботи й не підтвердження фактичної бізнес-готовності.

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

## Статус реєстру після PR #39

- **#39 створює перевірюваний артефакт, не закриває бізнес-приймання.** `docs/BACKLOG_ACCEPTANCE_LEDGER.json` відтворюється через `python backlog_audit.py`; `--check` перевіряється у звичайному CI. Документи: `docs/BACKLOG_RECONCILIATION.md` та `docs/BA_GOLD_CASE_ACCEPTANCE.md`.
- Зі 129 вимог **38 отримали конкретні code locator, 36 з них також test locator**, решта 91 потребує ручного зіставлення. Відсутність прив'язки не означає відсутність коду. Всі `human_acceptance` залишаються `NOT_RECORDED`.
- Виявлено **9 груп потенційного перетину критеріїв** із VIS/QA/PERF, без автоматичного видалення бізнес-функцій. Після злиття #39 лишається **9 тематичних PR #40–48** за первинним планом, плюс 2–3 окремі етапи приватного людського UAT.

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

### Post-#40 update

PR #40 implements verified source-cache invalidation and strictly one-to-one REST↔supplier candidate pairing. **Live Kibana authorization, verified supplier contract mapping and gold-set BA acceptance remain open**: engineering success is not human signoff. Next package is #41, focused on source-backed Jira task drafts, recipients, supplier XML attachment and manual email handoff.

### Post-#41 update

The generated email no longer asserts a verified supplier archive when only a subset of required Jira flow ZIPs is current. Standalone normalization is conservative; unknown readiness is a QA blocker. Real recipient routing, supplier method approval, Jira output accuracy and manual sending remain independent BA gates. Next thematic package: #42 (rapid action/focus cycle).

### Post-#42 update

A single in-memory last-local-DONE undo provides a fast correction protected by SQLite CAS; it does not change Jira, email or official sprint ordering. Remaining QUICK/FOCUS improvements are candidates for measured human UX acceptance, not automatically mandatory code. #43 focuses sprint/WRITE invariants, scored effort and truthful performance diagnostics.

### Post-#43 update

Hard sprint/WRITE/DONE ordering is protected by additional score-extreme tests. Supplier addresses are now explicit opt-in suggestions rather than being silently inferred from the task title. Actual recipient correctness and BA time-to-action are not established by this code. Next package #44 targets error-series RCA/source-retention semantics and reproducible counterexamples.

### Post-#44 update

Error-code-specific RCA now offers at most ten separate same-issue/supplier contrast candidate flows where that code was not observed. Contrast is neither a successful operation nor statistical causality; full authenticated source and independent expert UAT remain required. Next #45: bounded recovery/security hardening.

### Post-#45 update

A safe UTC creation-identity check now ensures forged or clock-skewed SQLite manifests cannot masquerade as valid recent backups, without auto-restoring or deleting old valid data. Windows hard-crash, antivirus locks, BitLocker/ACL and real rescue remain explicit UAT gates. #46 is performance/long-session reliability.

### Post-#46 update

Synthetic Chromium now records cold reload and debounced search across 100/500/1000 rows; punctuation-only tokens cannot spuriously match the entire list. These are CI diagnostics, not proven Windows device SLO or measured user time-to-action. Next #47: lean visible UI and optional feature rationalization. Final #48: backlog reconciliation against actual merged commits, unresolved human UAT/desktop deployment.

### Post-#47 update

The existing queue has semantic group headings and a non-hover accessible low-confidence quick hint; synthetic Chrome tests include 320px forced-colors, reduced-motion, focus outline and visible email actions. No actual NVDA/Windows/400% zoom or human 20–30 gold-case timing claim. Final #48 must reconcile merged code with the acceptance ledger while retaining these explicit UAT blockers.

### Post-#48: scoped code package closure vs actual product acceptance

PR #39–48 constitute the planned *engineering* sequence, conditional on #48 being reviewed, green and merged. The canonical 129 original requirement statuses were **not falsely rewritten as DONE**. `release_readiness.py` reports `BLOCKED_INDEPENDENT_UAT` because all real BA/Windows signoffs still lack independent evidence. Any future work to close QA-02/03/10/13 and actual Windows deployment is a separate explicit acceptance/operations activity, not silently claimed by this merge series. Optional P2/P3 decisions remain visible.
