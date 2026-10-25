# CCON BA Desk — єдиний реєстр можливостей і backlog

**Версія реєстру:** 2026-10-25 · **джерело правди:** `docs/PRODUCT_BACKLOG.md` · **власник:** один BA, лише його Jira-задачі.  
**Базовий код:** `main` після PR #30 (v2.30). **Поточний кандидат:** PR #31 (v2.31), великі черги, кеш нормалізованого пошуку і JSON відповіді, тестові 100/500/1000 задач; Windows/browser UX UAT окремо.  
**Межа:** GitHub CI доводить коректність синтетичних тестів, **не** доступність живої Jira/Kibana, повноту реальних логів або правильність бізнес-аналізу.

## 0. Продуктовий контракт, що не підлягає зміні без окремого рішення

1. **Одна людина.** У черзі й аналізі лише призначені мені Jira-задачі; з пов'язаних задач читати лише необхідний контекст, не додавати чужі задачі до моєї черги.
2. **Пріоритети:** підтверджений активний sprint завжди перед backlog; **усередині кожного рівня задачі з реальною потребою написати листа перед рештою**, далі корисні дії, ризики, 0–100. Опціональна чернетка листа сама по собі не означає `needsEmail=true`.
3. **Зберегти вигляд сторінки.** Стандартна картка і поточні секції, без режимів Quick/Deep/Email, нових вкладок/редизайну. Детальну аналітику ховати у вже наявних `details`.
4. **Головний результат:** точний, структурований, максимально лаконічний **англомовний опис Jira Task**. Не обмежувати 2 реченнями: додавати тільки речення з новою технічною інформацією, зберігати назви полів, регістр, AND/OR, expected output і QA.
5. **Кожна задача:** опціональний готовий **редагований лист**, незалежно від сигналу WRITE, але нічого автоматично не надсилати; зберігати ручні чернетки, адресатів, рішення й нотатки.
6. **ZIP для аналізу** = REST requests/responses + REST errors + **тільки** supplier-папка відповідного постачальника. **ZIP для листа** = **тільки XML потрібного supplier**, без REST, errors та інших suppliers. Готувати за наявності авторизованих flow незалежно від `needsEmail`.
7. Вхідний REST request → перетворення → supplier request; supplier response → перетворення → REST response. Не підмінювати кореляцію доказом mapping чи причини збою.
8. **Локальний Codex/Work** користується наявною авторизованою браузерною сесією Jira/Kibana/CCON, коли це можливо; не вилучати cookies, TOTP, токени й не відправляти корпоративні логи в публічний GitHub. Вебсервер Python не має власного інтерактивного браузера.
9. Jira та Confluence тільки read-only, листи тільки як drafts. Ніякого автоматичного запису, зміни тасок чи зовнішніх листів.
10. **Тематичні пакетні PR:** групувати 3–5 суміжних пунктів за спільними контрактами, тестами та ризиками; для кожного пакета перевіряти Python/Node/release/Compose до merge і CI на `main` після merge. Великий розмір не замінює перевірку.

## 1. Легенда

- **IMPLEMENTED (code):** є механізм і автоматичні тести; реальна інтеграція може бути не перевірена.
- **PARTIAL:** корисний фундамент є, але бракує частини критеріїв приймання або верифікації.
- **NEXT:** заплановано наступними 1–2 PR.
- **PLANNED:** ще не реалізовано.
- **DEFERRED:** вирішено поки не робити, але важливо зберегти в реєстрі.
- **GATE:** перевірка/зовнішня умова, а не готова функція.

## 2. Повний функціональний backlog

| ID | P | Стан | Функція / що має бути | Критерій готовності / наступний крок |
|---|---|---|---|---|
| CORE-01 | P0 | IMPLEMENTED (code) | Персональний повний Jira sync: descriptions, comments, linked issues, blockers | Повний JQL scope без пропущених сторінок; live Jira UAT |
| CORE-02 | P0 | IMPLEMENTED (code) | Абсолютний пріоритет перевіреного active sprint | Board ID; in-sprint вище backlog навіть при 0 vs 100; UAT |
| CORE-03 | P0 | IMPLEMENTED (code) | Друга перевага для задач, де треба лист | WRITE/needsEmail на початку свого sprint/backlog рівня; не підміняти резервною чернеткою |
| CORE-04 | P0 | IMPLEMENTED (code) | 0–100 із п'ятьма факторами та поясненням | businessImpact, urgency, dependencies, baDecision, actionability; compare real queue |
| CORE-05 | P0 | IMPLEMENTED (code) | Збереження manual status, notes, email draft між sync/refresh | Жоден імпорт AI не переписує ручних змін |
| CORE-06 | P0 | IMPLEMENTED (code) | New/updated/reopened/done/left-scope daily delta | Verified Jira Done ≠ disappeared from JQL; tests + live UAT |
| CORE-07 | P1 | IMPLEMENTED (local revision history); real UAT pending | Повний task-history 360° з ревізіями рішень/листування | Зберігати й порівнювати snapshots, аналіз, відповідь, дату, джерело |
| CORE-08 | P1 | IMPLEMENTED (human action plans); real UAT pending | Personal action plan / черга на сьогодні | Що перевірити, кому написати, хто блокує, next follow-up, робочий стан |
| CORE-09 | P2 | IMPLEMENTED (supplier, method, technical fields, links in existing search); UAT pending | Швидкий пошук і фільтрація за методами, supplier, issue, залежностями | Search/filter без переробки основної картки |
| CORE-10 | P2 | PARTIAL (v2.19 daily score/factor delta + human review warnings; long-term bias UAT open) | Узгодженість оцінок між задачами та ретроспектива пріоритетів | Виявляти великі зміни без нового Jira fingerprint; AI bias не доведено автоматично |
| BA-01 | P0 | PARTIAL (exact confirmed field, enum literal, AND/OR and QA structural checks; expert UAT open) | Готовий короткий англомовний task description | Кожна умова IF/THEN, field, expected output, QA зчитані коректно; human gold set |
| BA-02 | P0 | PARTIAL (no false attachment claims + method coherence checks; human semantic UAT open) | Готовий фактологічний emailDraft для **кожної** задачі | Незалежно від WRITE; не вигадувати адресата/метод/прикріплений ZIP; коректний follow-up |
| BA-03 | P0 | IMPLEMENTED (code) | 30-second context: confirmed/current/target/action/why | Зрозумілий стислий briefing із proof/uncertainty |
| BA-04 | P0 | IMPLEMENTED (mechanical excerpt gate); semantic UAT open | Source-grounded facts vs interpretations vs assumptions | Для кожного важливого твердження source offset/URL і support test |
| BA-05 | P0 | PARTIAL | BA questions ID, status, owner, answer, evidence | OPEN → ANSWERED / SUPERSEDED / NOT_APPLICABLE; пропажа з AI ≠ answered |
| BA-06 | P1 | IMPLEMENTED (new-comment candidates); semantic UAT pending | Розпізнавання реальної відповіді на питання з Jira/документів | Запропонувати кандидата відповіді з цитатою; без auto-close |
| BA-07 | P0 | IMPLEMENTED (explicit rule/QA references); real-case UAT open | Requirement → QA traceability | Зіставити позитивні/негативні/edge-cases із кожною підтвердженою вимогою |
| BA-08 | P1 | IMPLEMENTED (approved-model single-task CLI); live UAT open | On-demand deep re-analysis однієї задачі | Перезапуск без повного щоденного проходу, повага до збережених ручних правок |
| BA-09 | P1 | PARTIAL (v2.24 local Confluence handoff, exact-quote gate, missing/variant signals; semantic/version UAT open) | Related Jira + wiki/documentation cross-check | Читати доступні джерела, фіксувати непрочитані та конфлікти |
| BA-10 | P1 | IMPLEMENTED (local event history); human UAT pending | Decision register: confirmed/superseded/disputed | Хронологія рішень, хто підтвердив, коли, що змінюється |
| BA-11 | P2 | IMPLEMENTED (human approved reference and diff); UAT pending | Порівняння готової чернетки з останнім погодженим текстом задачі | Не переписувати схвалене без необхідності |
| EVD-01 | P0 | IMPLEMENTED (code) | Зчитування повного ZIP за шарами REST/errors/selected supplier | Ніякого аналізу чужих supplier папок; parsing and ZIP safeguards |
| EVD-02 | P0 | IMPLEMENTED (code) | Виявлення shared-flow/correlation кандидатів | Без фальшивої впевненості у спарюванні |
| EVD-03 | P0 | PARTIAL | REST request→supplier request; supplier response→REST response value equality/difference | Позначати `CANDIDATE_ONLY`; підтверджувати transformation rule проти специфікації |
| EVD-04 | P0 | IMPLEMENTED (code) | Supplier-only ZIP для листа з перевіреною цілісністю | Лише XML конкретного supplier; не залежить від needsEmail |
| EVD-05 | P0 | IMPLEMENTED (local handoff); live browser UAT pending | Автоматизоване завантаження авторизованих CCON ZIP через локальний Codex | Flow plan вже є; реально перевірити браузер→локальний ZIP→ingest→download |
| EVD-06 | P0 | PARTIAL | Kibana discovery по issue, cconFlowId, error links | Action plan вже є; потрібні локальні браузерні перевірки |
| EVD-07 | P0 | IMPLEMENTED (code); live UAT pending | **Kibana error-series: до 30 репрезентативних випадків однієї помилки** | Дедуп flow, групування за error code/stage/method, coverage/gaps, proof links, без змішування supplier |
| EVD-08 | P0 | IMPLEMENTED (code); live UAT pending | **RCA evidence matrix: що підтверджено, що лише гіпотеза** | Hypothesis/alternative/counterexample/missing proof; заборона фальшивої definitive cause |
| EVD-09 | P1 | IMPLEMENTED (contract-shape candidates); live contract UAT pending | Детальний endpoint/method mapping і контракти request/response | Розрізняти REST та supplier native method, status/field/null/repetition |
| EVD-10 | P1 | PARTIAL (heuristic taxonomy, source origin unverified) | Error taxonomy та регресія по кількох supplier версіях | Bad request, provider reject, mapping, timeout, CCON internal із підтвердженим stage |
| EVD-11 | P1 | IMPLEMENTED (explicit payload timestamps); Kibana live timeline UAT pending | Часова послідовність по flow з Kibana timestamps | Причинно-часові залежності, pagination, timezone, retries |
| EVD-12 | P1 | IMPLEMENTED (local flow coverage with explicit missing sources); live UAT open | Confidence+coverage dashboard для доказів | Відсоток flows із REST+supplier+errors, причини прогалин |
| EVD-13 | P1 | PARTIAL (v2.24 local JSON/XML/ZIP text, optional PDF reader, Confluence HTML handoff; real UAT open) | Вкладення Jira (PDF/JSON/XML/ZIP), Confluence/wiki | Read-only extraction, не просто метадані; bounded/safe parser, source audit |
| EVD-14 | P2 | PARTIAL (distinct-flow recurrence + explicit flow-event windows; no production prevalence) | Cross-case anomaly detection: recurring errors across time | Порівняння case signatures з попереднім аналізом без PII |
| EVD-15 | P2 | PARTIAL (opt-in dry-run retention/quota, pinned-index protection, local decision audit; encryption & ACL validation open) | Кероване зберігання raw ZIP: retention, cleanup, quota | Encrypt-at-rest/ACL, TTL, аудит, no commit/no egress |
| OUT-01 | P0 | PARTIAL (unresolved questions/rules block premature READY_FOR_REVIEW) | Самодостатній BA dossier із короткою дією, правилами, QA, gaps | Реальні приклади без зайвих формулювань; scenario-based grading |
| OUT-02 | P0 | PARTIAL | Чернетка листа, subject/method, контекст попередніх відповідей | Ситуативне формулювання, ручне редагування, без auto-send |
| OUT-03 | P1 | IMPLEMENTED (code); live UAT pending | Готовий supplier ZIP та evidence status без прихованої недоступності | Показувати ready/stale/blocked + причина і flow у поточній картці |
| OUT-04 | P1 | PARTIAL (v2.24 Jira/verified local document quote gate; human semantic truth UAT open) | Контроль фактичності вставлених доказів і PDF/логів | Кожна вимога та тест мають джерело, або чітко OPEN |
| UX-01 | P0 | IMPLEMENTED (code) | Зберігати стандартну сторінку, без окремих режимів | Меню/поля/status/email/лог ZIP збережені |
| UX-02 | P1 | PARTIAL (v2.25 exact adjacent generated-line dedup and in-place density hints, semantic gold-set UAT open) | Compact descriptions і progressive disclosure | Скорочення повторів, не ховати основний результат |
| UX-03 | P2 | PARTIAL | AERTiCKET-inspired branding | Дійсні токени/логотип потребують brand approval |
| UX-04 | P2 | IMPLEMENTED (copy/edit mail, next/save); live UAT open | Copy task/email + quick next/open/save | Можливість проходити список без зайвих кліків, UAT |
| QA-01 | P0 | IMPLEMENTED (code) | Python/Node/Release/Compose CI | Required checks + merge only when green |
| QA-02 | P0 | GATE | Live Jira + Kibana + CCON auth UAT з 2–3 реальними задачами | Browser session, 1 normal flow, 1 multi-error flow, 1 ambiguous flow |
| QA-03 | P0 | GATE (v2.25 frozen 20–30 case deterministic preflight wired; real human scores still required) | Реальні 20–30 gold cases, blinded AI vs analyst | Measure false facts, missed conditions, task/edit quality |
| QA-04 | P1 | PARTIAL (v2.25 case-level warning counts, source/QA deficits and A/B deltas; business-truth metrics require real reviewers) | AI quality metrics, reject invalid dossier | Structured schema / briefing/factors checks implemented; factual support pending |
| QA-05 | P1 | PARTIAL | Safe daily prompt calibration checklist | Whitelisted diagnostics implemented; prompt version change evaluated separately |
| QA-06 | P1 | IMPLEMENTED (staged A/B + human approval + rollback); real reviews pending | Prompt A/B regression / automatic candidate proposal | Human gate, compare gold set, rollback, no unreviewed auto-prompts |
| QA-07 | P2 | PARTIAL (synthetic AF/KL/Finnair multi-error, retry, malformed and nested ZIP matrix; live formats UAT open) | Offline fixtures for realistic REST/XML/multi-error formats | Coverage by supplier method, nested ZIP cases, pagination, retries |
| QA-08 | P1 | PARTIAL (v2.20 model egress sanitizer and synthetic regressions; full DLP/log audit pending) | Data minimization/security for prompt, manifests, debug logs | PII/credentials, safe link stripping, prompt injection regression |
| INF-01 | P3 | DEFERRED | Cloud deployment: SSO/OIDC/HTTPS/hosting | Cloud pilot code exists, real infra and security approval not started |
| INF-02 | P3 | DEFERRED | Backups, PostgreSQL, multi-worker safety, operations alerts | After local feature quality/infra approval |
| INF-03 | P3 | DEFERRED | Real unattended scheduling and live model setup | Does not block local Codex project |
| INF-04 | P3 | DEFERRED | Formal secrets manager, brand/legal approvals | Production security gate |

## 2A. Продуктивність BA: UX/UI, швидке виконання, performance, reliability і повне покриття

**Пріоритизація:** P0 = довіра до пріоритетів, цілісність даних, швидка критична дія, відсутність блокувального лагу; P1 = прискорення типового потоку; P2 = polish/операційна підтримка після UAT. `NEXT` = кандидат наступного PR, не реалізовано. Зміни не мають порушувати незмінні інваріанти §0.

| ID | P | Стан | Результат для користувача | Acceptance / proof |
|---|---|---|---|---|
| QUICK-01 | P0 | IMPLEMENTED (v2.28 top-of-card current next action; 5-sec human comprehension UAT open) | Показати одну однозначну Next Action above the fold, не розгортати 4 секції | ≤5 с comprehension; J-03, J-06; KEEP existing page |
| QUICK-02 | P0 | PARTIAL (v2.28 structurally checked one-click Jira draft copy; 5-click handoff measurement open) | Copy verified Jira description + Save/Next у спільному маршруті | ≤5 intentional actions; zero Jira write; J-03/J-08 |
| QUICK-03 | P0 | PARTIAL (v2.28 explicit manual completion confirm; actual sent/delivered event evidence still manual) | Відділити Copy/Open Mail від фактичної Sent/Delivered події | Human confirmation and timestamp; no fabricated delivery proof |
| QUICK-04 | P1 | PLANNED | Зберегти короткі recipient/method/ZIP readiness checks перед mailto | No false ready for missing ZIP/method/recipient; J-04 |
| QUICK-05 | P1 | PARTIAL (v2.29 identifies quick candidates without reordering any lane/score/group; batch workflow pending) | Batch quick handoffs тільки у межах коректного lane | Sprint/WRITE contract unchanged; reordering by time opt-in only |
| QUICK-06 | P1 | PLANNED | Reversible manual Done / Undo без зовнішніх API записів | Cancel/reverse with preserved notes; J-08 |
| QUICK-07 | P1 | PLANNED | Compact card action/proof line без шуму з чіпів | User 5-second scan, no loss of proof status |
| QUICK-08 | P2 | PLANNED | Кандидатні шаблони для повторюваних дрібних BA задач | Template never invents source/method; gold QA |
| FOCUS-01 | P0 | PARTIAL (v2.28 retain selected key, list scroll and open details on same-task refresh; browser UAT open) | Зберігати selected task і позицію списку при оновленні | No jump on background import, user edits preserved; J-07 |
| FOCUS-02 | P0 | PARTIAL (v2.30 tab-local selected issue, scroll/disclosures and caret coordinates; browser UAT pending) | Відновлення scroll, open details, cursor при поверненні | Resume p95 goal ≤45 s; browser UAT |
| FOCUS-03 | P1 | PARTIAL (v2.30 Alt+arrow, / search, Alt+C, Ctrl/Cmd+Enter; keyboard UAT pending) | Keyboard shortcuts Next / Search / Copy / Save із захистом input focus | Keyboard-only critical path A-01; no destructive collision |
| FOCUS-04 | P1 | PLANNED | Розділити high-signal інфо та deep evidence в existing details | No extra tabs/modes; J-03/J-06 |
| FOCUS-05 | P1 | PLANNED | Sticky next-action/progress microheader в існуючій detail pane | No page redesign; responsive A-03/A-04 |
| FOCUS-06 | P1 | PARTIAL (v2.30 never rerender focused detail, restore keyboard row and typed cursor; browser traces pending) | Захист від фонових тостів/DOM rerender під час набору тексту | No focus loss, cursor jump, stale overwrite |
| FOCUS-07 | P2 | PLANNED | Pin personal deep-work task без зміни official Jira priority | Manual pin only within lane; clear override and reset |
| FOCUS-08 | P2 | PLANNED | Відновити фокус після bulk dialog/mailto/error | A-01/A-11; action accessible |
| PRIOR-01 | P0 | PARTIAL (v2.29 manual XS–XL persisted + LOW confidence heuristic; real effort calibration pending) | EffortEstimate XS/S/M/L/XL/UNKNOWN, provenance and confidence | Human-reviewed or source-derived; never business truth guess |
| PRIOR-02 | P0 | PARTIAL (v2.28 visible existing lane/WRITE/signal/score/blocker breakdown, human validation open) | Explain order: sprint → real WRITE → signal → score → blocker | Ranking reason for 100% selected tasks; J-02 |
| PRIOR-03 | P0 | PARTIAL (v2.29 combinatorial status/sprint/signal/score invariants; broad randomized tests next) | Hard invariant tests for all sprint/WRITE/Done/stale permutations | Property-based synthetic test set, no cross-lane promotion |
| PRIOR-04 | P1 | PARTIAL (v2.29 display-only quick-win hints; UX evidence/time-to-handoff pending) | Visible quick win candidates only in same hard-priority bucket | Time benefit cannot overtake urgent sprint/blocker |
| PRIOR-05 | P1 | PLANNED | Separate impact, urgency, effort and unblocking from arbitrary speed score | Explainable, human acceptance > 90% ordering confidence |
| PRIOR-06 | P1 | PLANNED | Waiting sweep follow-up due date and owner with no repeat letter | Due status visible, source-backed, J-05 |
| PRIOR-07 | P2 | PLANNED | Time-to-handoff metrics by real work archetype | Local opt-in, no PII, no cloud telemetry |
| PRIOR-08 | P2 | PLANNED | Feedback on wrong priority captured as manual correction | Never silently retrain queue ranking; human UAT |
| PRIOR-09 | P2 | PLANNED | Show weekly WIP / blockers / completion versus rework | Not a gamified Done count, J-01 |
| UI-05 | P1 | PLANNED | Density and hierarchy audit at 320/768/1440 viewport | A-03; no horizontal overflow/hidden primary action |
| UI-06 | P1 | PARTIAL (v2.30 unsaved/saving/error/CAS conflict states; real error and screen reader UAT open) | Clear statuses saved, unsaved, saving, failed, stale | A-07/A-12 and race tests |
| UI-07 | P1 | PLANNED | Distinct empty / unavailable / permissions / stale / no matches states | Correct recovery action in each state |
| UI-08 | P2 | PLANNED | Readable PNR/field/code formatting and safe wrapping | No truncation in clipboard/export, A-06 |
| UI-09 | P2 | PLANNED | Default collapsed evidence sections after human 5-sec test | Keep main results visible, never bury next action |
| UI-10 | P2 | PLANNED | Visual diff regression for existing layout and copy buttons | Snapshot on 3 viewport sizes; no brand approval bypass |
| PERF-01 | P0 | IMPLEMENTED (v2.26 code; live measurements pending) | Monotonic SQLite revision + light task token endpoint | P-01..P-08 + HTTP auth and payload reduction |
| PERF-02 | P0 | IMPLEMENTED (v2.26 code; browser UAT pending) | Load full tasks only on revision change, hidden tab idle | P-02/P-11/P-12, no false staleness |
| PERF-03 | P0 | IMPLEMENTED (v2.26 code; browser UAT pending) | Skip expensive no-query search path and early reject | P-09/P-10, Unicode and sprint regression |
| PERF-04 | P1 | IMPLEMENTED (v2.31 debounced search, per-snapshot Unicode index, exact parity tests; Windows p95 UAT open) | Debounced full-text search with cached per-snapshot index | Search p95 target ≤100 ms at 1000 rich tasks |
| PERF-05 | P1 | PARTIAL (v2.31 delegated clicks and focused-row update without full list repaint; windowing requires browser profiling) | Event delegation and scrolling for large task list | No focus/aria regression; compare 500/1000 |
| PERF-06 | P1 | IMPLEMENTED (v2.31 immutable full-JSON bytes cache by transactional SQLite revision + error; external writer tests) | Cache full server serialized task read by committed revision | Atomic invalidation on import/save; concurrent tests |
| PERF-07 | P1 | PARTIAL (v2.31 reproducible Python/Node 100/500/1000 synthetic timings in CI; real browser/8h UAT open) | Benchmark browser cold/warm, DOM scripting/paint, 8h session | Named Windows machine p50/p95, memory trend |
| PERF-08 | P1 | PLANNED | Avoid repeated heavyweight detail fetch on list refresh | Fetch selected only on selection/revision, compare versions |
| PERF-09 | P2 | PLANNED | Simplify 1374-line CSS cascade after visual/a11y regression | No unexpected fonts/spacing/contrast changes |
| PERF-10 | P2 | PLANNED | Evaluate SQLite WAL, busy timeouts and JSON index with empirical trace | Do not enable blindly; Windows/backup compatibility |
| REL-01 | P0 | IMPLEMENTED (v2.27 per-task SQLite CAS, 409 and human resolution; live browser UAT open) | Per-task optimistic concurrency token and stale edit conflict UX | Two tabs cannot silently overwrite each other's note/draft |
| REL-02 | P0 | PARTIAL (v2.27 recovered drafts pin original revision, explicit conflict; power-loss multi-tab recovery UAT open) | Atomic user-draft recovery and edit revision validation | Forced close/reopen/reload leaves acknowledged edits intact |
| REL-03 | P0 | NEXT | Safe backup/restore of private SQLite + manifest without export secrets | Crash drill, documented recovery and permissions |
| REL-04 | P1 | PLANNED | Watcher failure/retry diagnostics without toast spam | No error swallowed; error state shown, P-12 |
| REL-05 | P1 | PLANNED | Graceful server shutdown and restart during import | No database damage/partial save, Windows UAT |
| REL-06 | P1 | PLANNED | Data validation and schema migration matrix across releases | v2.23→current, old DB revision initialized once |
| REL-07 | P1 | PLANNED | Retry strategy for recoverable local API failures with idempotency | No duplicate mailto or Done, bounded retry |
| REL-08 | P1 | PLANNED | OS folder permissions/encryption checks for private local ZIP | Fail closed/notice for insecure ACL configuration |
| REL-09 | P2 | PLANNED | Bound old history/reports while preserving important user audit | No unexpected data deletion, archive user-approved |
| REL-10 | P2 | PLANNED | Safe signed release/backup metadata and rollback rehearsal | Verify hashes; old app loads additive migration |
| A11Y-01 | P1 | PARTIAL (v2.30 native keyboard shortcuts and guide; screen reader & real keyboard UAT open) | Keyboard full quick-task flow + shortcuts usability | A-01/J-03/J-08 with focus protection |
| A11Y-02 | P1 | NEXT | 200%-400% zoom and 320px mobile acceptance | A-03/A-04; primary actions reachable |
| A11Y-03 | P1 | PLANNED | Screen reader semantics for task list, selected and status | A-02, announcements not noisy |
| A11Y-04 | P1 | PARTIAL (v2.30 native modal Close initial focus and return focus on close/Escape; browser UAT open) | Bulk email dialog focus trap/return, escape | A-11; no unintended send |
| A11Y-05 | P2 | PLANNED | Forced color/high contrast and reduced-motion support | A-05/A-10 |
| A11Y-06 | P2 | PLANNED | Readable labels/tooltips without mouse hover | A-09 and touch accuracy |
| QA-09 | P0 | PARTIAL (v2.31 synthetic 100/500/1000 CI + exact ranking parity; Chrome/Edge E2E pending) | Synthetic 100/500/1000 browser E2E performance baseline | Windows DevTools p95 + startup/long session |
| QA-10 | P0 | GATE (v2.29 synthetic archetype cases; observed BA handoff times and semantic review not performed) | Human observation of 5 BA task archetypes, repeated runs | TTNA/TTSH/MRI with 0 critical false-ready decisions |
| QA-11 | P0 | PARTIAL (v2.27 synthetic concurrent instances/restarts/conflicts; real browser crash drill open) | Cross-tab edits, stale conflict and crash recovery integration | P-15/P-17/P-18, 0 silent overwrite |
| QA-12 | P1 | NEXT | DOM behavior tests with approved Playwright/browser runner | Focus, click, screenreader, history, network reconnect |
| QA-13 | P1 | PLANNED | Local-only 20–30 real-case semantic BA handoff study | Actual independent gold scores, not CI counts |
| QA-14 | P1 | PLANNED | Quantified code/branch coverage baseline, gaps by critical path | No invented 100%; dev-only tooling approval |
| QA-15 | P2 | PLANNED | Scheduled offline regression drill on diverse machine profiles | OS, Python version, locale, browser, power mode |
| OPS-01 | P1 | NEXT | Standard synthetic performance smoke + fixed cohort sizes | Repeatable local script and measurement doc |
| OPS-02 | P1 | PLANNED | Private local diagnostic bundle with PII redaction and consent | No production logs by default; explicit export |
| OPS-03 | P1 | PLANNED | Version/upgrade and roll-back steps for local task scheduler | Main merge does not update installed local copy |
| OPS-04 | P2 | PLANNED | Error budget dashboard for local app only, opt-in | No remote telemetry or background transfer |
| OPS-05 | P2 | PLANNED | Daily clean startup health checklist with offline fallback | Speed and accurate stale flags |
| SEC-01 | P0 | PARTIAL (v2.27 CAS in new UI, legacy no-token API remains compatible; stronger enforcement after migration) | Cross-tab and concurrent browser save authorization plus revision CAS | No CSRF/security relaxation |
| SEC-02 | P1 | PLANNED | Full localhost/cloud auth tests for new small endpoints | Host restrictions and current OIDC origin untouched |
| SEC-03 | P1 | PLANNED | No personal/Jira/source content in perf report or public CI | Synthetic samples only; cross-check on PR |
| SEC-04 | P2 | PLANNED | Browser storage retention and private recovery data review | No stale PII in unsafe storage without retention policy |

**Визначення effort (не змінює Jira/score):** XS ≤2 хв, S 2–5 хв, M 5–20 хв, L 20–60 хв, XL >60 хв, UNKNOWN. Estimate — окремий факт із confidence/джерелом, а не прибуток у priority formula. Реальний WRITE залишається попереду інших сигналів у тому самому sprint/backlog lane. High-risk blockers залишаються вищими за номінальний quick win при однакових нормативних пріоритетах.

**Критичні критерії:** не втрачено manual edit; нуль false claims у human gold set; та сама активна sprint послідовність; без external writes/send; P95 interaction зафіксовано на вказаному Windows hardware, а не вигадано. `docs/PRODUCTIVITY_UX_AUDIT.md` містить продуктовий аналіз, `docs/LOCAL_PERFORMANCE_RELIABILITY.md` — технічні SLO/бенчмарки, `docs/UX_TEST_COVERAGE_MATRIX.md` — тестовий evidence matrix. Загалом **73 нових конкретних backlog items**, включно з частково реалізованими PERF-01..03.

### Групування наступних PR після продуктової оцінки

1. **#26 current: PERF-01/02/03 + OPS-01 + QA coverage:** протокол зміни ревізії, пошук без зайвої роботи, синтетичний benchmark, інтеграційні тести і цей повний audit; без UI-перебудови.
2. **#27 current: REL-01/02 + SEC-01 + QA-11:** per-task revision compare-and-swap, recovery, two-tab conflict notice and undo, щоб виключити last-writer-wins.
3. **#28 current: QUICK-01/02/03 + FOCUS-01 + PRIOR-02:** максимально швидкий read → verified artifact → handoff → record → next в існуючій картці; тест 5 archetypes.
4. **#29 current: PRIOR-01/03/04 + QUICK-05 + QA-10 groundwork:** effort-aware review hints в незмінній sprint/WRITE lane, transparent ordering and timed BA UAT.
5. **#30 current: FOCUS-02/03/06 + A11Y-01/04 + UI-06:** keyboard/navigation/focus+dirty warning regression.
6. **#31 current: PERF-04/05/06/07 + QA-09 groundwork:** browser traces and measured large-list optimizations, WCAG/browser proof.
7. **#32+:** A11Y-02/03/05, REL-03/04/05, UX polish, all other backlog rows; prioritize from actual field measurements and human BA gold set.

**Dependency rule:** conduct QA-10 human observation before changing task ordering, manual Done behavior or showing effort as absolute truth. Browser E2E instrumentation requires approved runner, no corporate data in public CI. Do not claim full business correctness from passing synthetic tests.

## 3. Тематичні пакетні PR / порядок

| Блок | Згрупований обсяг | Гейт |
|---|---|---|
| **#9 — CODE COMPLETE; LIVE UAT OPEN** | EVD-07: 1–30 error cases з локально підготовлених flow reports; EVD-08: evidence-based RCA із альтернативами й прогалинами | Synthetic multi-flow regression + flow/supplier isolation + baseline CI. Реальний Kibana UAT окремо |
| **#10 — CODE COMPLETE; LIVE BROWSER UAT OPEN** | EVD-05: локальний browser-to-ZIP handoff із журналом помилок; OUT-03: ready/stale/blocked ZIP в existing card | Реальний авторизований download без cookies/API leaks |
| **#11 — CODE COMPLETE; HUMAN CONTENT UAT OPEN** | BA-04 + OUT-04: перевірка зв'язку claim→source; BA-07: QA traceability | Невідтворювана вимога залишається OPEN |
| **#12 — CODE COMPLETE; LIVE UAT OPEN** | BA-06: question answer suggestions; BA-10: decision register | Не закривати питання автоматично |
| **#13 — CODE COMPLETE; LIVE UAT OPEN** | EVD-09/EVD-11: mapping contracts + flow timeline | Два request paths, retry/timeout, ordering |
| **#14 — CODE COMPLETE; LOCAL UAT OPEN** | CORE-07/CORE-08: history + personal action plan | Один екран, current vs previous, overdue |
| **#15 — CODE COMPLETE; LIVE UAT OPEN** | BA-08/UX-04: one-task reanalyze + copy workflow | User edits untouched |
| **#16 — CODE COMPLETE; REAL GOLD-SET UAT OPEN** | QA-03/QA-06: frozen gold-set + human-approved prompt A/B | No critical false claims |\n| **#17–18 — CODE COMPLETE; LIVE UAT OPEN** | EVD-10/12/14 (частково), CORE-09, BA-11 | Перевірка реальних Jira/Kibana даних |\n| **#19 — MERGED; HUMAN UAT OPEN** | CORE-10: щоденний score delta, зміни факторів, пояснювальні попередження | CI green, без auto-ranking |\n| **#20 — MERGED; SECURITY UAT OPEN** | QA-08: безпечна мінімізація даних перед відправленням у схвалену модель | Synthetic prompt payload, URL/PII/secrets tests + CI |\n| **#21 — MERGED; BROWSER UAT OPEN** | EVD-13: локальний браузерний handoff JSON/XML/ZIP, прив'язка доказів до Jira fingerprint | ZIP safety, structure only, PDF explicitly unread |
| **#22 — MERGED; LIVE UAT OPEN** | EVD-15 (ZIP lifecycle/quota) + EVD-14 (strict temporal recurrence) + QA-07 (realistic synthetic fixtures) | CI on PR & main green, host ACL/encryption unverified |\n| **#23 — MERGED; HUMAN UAT OPEN** | BA-01/BA-02/OUT-01/QA-04: exact conditions, email evidence checks, dossier readiness | CI + semantic gold-case UAT, no Jira/email writes |\n| **#24 — MERGED; BROWSER UAT OPEN** | EVD-13 + BA-09 + OUT-04: local PDF/JSON/XML/ZIP text, Confluence browser handoff, verified quote cross-check | Zero raw document egress; source hash/fingerprint validation; CI + human UAT |\n| **#25 — MERGED; REAL GOLD-SET UAT OPEN** | UX-02 + QA-04 + QA-03 preflight: safe description dedup, in-place density warnings, local frozen 20–30 A/B metrics | Green CI, no actual gold-case verdict without independent human review |\n| **#26 — MERGED; WINDOWS PERFORMANCE UAT OPEN** | UX audit + PERF-01/02/03 + OPS-01 + local regression coverage; no redesign | Synthetic 100/500/1000 benchmark, CI green; Windows human UAT remains open |\n| **#27 — MERGED; REAL BROWSER UAT OPEN** | REL-01/02 + SEC-01 + QA-11: per-task CAS and conflict review | Python/Node CI; two real Chrome tabs still require UAT |
| **#28 — MERGED; QUICK-UX UAT OPEN** | QUICK-01/02/03 + FOCUS-01 + PRIOR-02: top-of-card next action, gated copy, manual done confirmation, queue explanation and scroll retention | CI + source-honest synthetic archetypes; real time-to-handoff UAT required |
| **#29 — MERGED; REAL EFFORT UAT OPEN** | PRIOR-01/03/04 + QUICK-05 + QA-10 groundwork: manual band, provenance-aware heuristic, quick hint, no reordering | Python/Node CI + 20–30 real-case effort/time calibration still required |
| **#30 — MERGED; LIVE KEYBOARD UAT OPEN** | FOCUS-02/03/06 + A11Y-01/04 + UI-06: shortcuts, per-tab context/caret, focus-safe refresh, honest save status | CI + synthetic keyboard policies, Windows/Chrome two-tab assistive-technology UAT open |
| **#31 — IN PROGRESS; BROWSER PERFORMANCE UAT OPEN** | PERF-04/05/06/07 + QA-09: cached rank/search/index/HTTP JSON + synthetic 100/500/1000 benchmarks; native DOM virtual list deferred | Exact Node parity, cross-process SQLite revisions and CI; real Windows DevTools p95/heap 8h pending |
| **Далі, GROUPED** | Real Jira/Kibana/Confluence UAT + model gold-set semantic review and feedback-driven iteration | Збереження приватних даних і ручних рішень, без автоматичної публікації |
| **Пізніше** | INF-01..04 (cloud/production) | Свідомо поза поточним scope |

### #27: фактичний обсяг і межі

- **Implemented:** per-task `manualRevision` on SQLite, additive migration, atomic compare-and-increment `UPDATE ... WHERE manual_revision=?`, HTTP `409 TASK_REVISION_CONFLICT`, revision returned in task list and successful save.
- **Implemented:** new browser writes pin the loaded version; recovered drafts keep their original baseRevision; conflict UI shows both sets locally and requires explicit confirmation to accept saved data or overwrite after review. No auto-Jira/edit/send.
- **Covered synthetically:** two concurrent Desk instances, 409/no last-write-wins, status-only preserve email, issue isolation, restart, snapshot reimport, legacy DB migration, DOM policy helper tests.
- **Open:** Chrome/Edge two-tab interaction and crash/restore UAT, formal cross-tab localStorage recovery isolation, legacy external API callers without CAS token; see next packages.
- **Policy:** unrelated global task revision is NOT a per-task edit conflict. An edited task's manualRevision is the only CAS token, incremented on manual writes; snapshot imports do not reset it.


### #28: швидка підготовка й передача результату без окремих режимів

- **Робоча дія:** наступний `nextActionUk` винесено на початок існуючої картки. Дубль нижче прибрано, збережені повні BA докази, технічні правила й редаговані чернетки.
- **Прискорена копія:** кнопка Jira-чернетки у верхній частині активується **лише** для актуального аналізу зі станом Quality Gate `STRUCTURALLY_VERIFIED`. Це перевірка структури, **не** схвалення фактичного змісту; BA перевіряє джерела та вручну передає текст. Заблоковані, невизначені або застарілі описи залишаються в деталях для перевірки.
- **Completion:** `Виконано → Далі` та ручний вибір DONE запитують, чи зовнішню дію справді виконано. Copy/mailto/Jira link ніколи не означають `sent`, `delivered` чи Jira Done.
- **Пріоритет:** згорнутий блок роз'яснює порядок із чинного `task-rules.mjs`: спринт, реальна потреба в листі, сигнал, 0–100, blocking. Алгоритм сортування **не змінено**.
- **Фокус:** оновлення того самого завдання зберігає активну вибрану задачу, прокрутку та розкриті `details`; фонова синхронізація не змінює typed drafts.
- **Гейт:** регресійні Node тести на готову, лист, REVIEW, BLOCKED, stale, WAIT, DONE й archived. Реальні метрики TTNA/TTSH, Chrome/Edge/Windows і доступність потребують окремого UAT.

### #29: реалізоване оцінювання обсягу

- **Власна оцінка:** поле XS/S/M/L/XL/UNKNOWN додається до звичного «Мій робочий стан». Зберігається як `manual_effort` в SQLite в CAS-транзакції разом з іншими правками. Старі DB автоматично отримають UNKNOWN; повторний імпорт Jira не скидає оцінку.
- **Підказка:** `assets/effort-planning.mjs` детерміновано оцінює лише структуровані метадані. `HEURISTIC / LOW` ніколи не видається за виміряний час. Ручне значення має `MANUAL / USER_SELECTED`.
- **Швидкі кандидати:** тільки READY/WRITE з актуальним аналізом, структурно перевіреним Gate і відсутніми питаннями. У списку це маленька підказка `S?` і лічильник, **жодного нового сортування**. XS з невідомими доказами не вважається quick win.
- **Перевірки:** матриця з 180 комбінацій status/sprint/signal/score × 6 варіантів effort плюс edge випадки для багатокрокових BA-задач, автоматична міграція старої DB, приватність, багато вкладок, збережений email/status.
- **Опис критеріїв і фактичні прогалини:** `docs/EFFORT_PRIORITIZATION.md`; без real UAT не заявляти, що оцінка тривалості точна або праця стала швидшою.

### #30: keyboard-first BA flow і відновлення контексту

- **Навігація:** у звичній черзі доступні `Alt+↑/↓` (тільки видимі задачі за чинним сортуванням), `/` (пошук), `Alt+C` (скопіювати актуальну дію), `Ctrl/Cmd+Enter` (збереження через CAS); показано у згорнутій підказці без нових режимів.
- **Захист редагування:** ввод у textarea/select/contenteditable не перехоплюється shortcut-обробником; modal/dialog блокує глобальні дії. Фонове оновлення не замінює DOM активної картки з фокусом/незбереженими правками, а фокус на рядку списку відновлюється після render.
- **Повернення:** обрана задача, scroll/open disclosures і позиція курсора зберігаються для цієї вкладки; лише номер задачі та технічні координати/хеші, без Jira-описів і текстів приватних чернеток.
- **Save UX:** `збережено / незбережено / зберігаю / помилка / конфлікт версій` тепер різні стани; ніякого «збережено» перед HTTP acknowledgment. Діалог пакетних листів повертає фокус на opener після Escape/Close.
- **Автоматичні тести:** `tests/focus-navigation.test.mjs` покриває чисту policy для клавіш, IME, модалки, фільтрів, disclosures, caret і privacy. Повні browser DOM E2E, вимірювання resume time і screen reader UAT залишаються OPEN.
- **Детальний runbook:** `docs/FOCUS_KEYBOARD_UX.md`.

### #31: великі черги без компромісу з пріоритетами

- **Implemented:** `assets/queue-performance.mjs` caches ranked queue, Unicode search text and already computed filter results for a snapshot; 130ms debounce; immediate navigation flush. `task-rules.mjs` maintains original fallback with optional cache provider. Exact source text/folded matching semantics maintained.
- **Implemented:** single delegated list click handler, selection `aria-pressed` and CSS toggled in place, keystrokes update only one unsaved marker instead of 1,000 DOM rows. Full list redraw still used after actual source/filter changes.
- **Implemented:** `Desk.view_json_bytes()` sends an immutable cached JSON response for unchanged SQLite revision/error with read-transaction snapshot consistency. The original object `Desk.view()` contract, local/cloud security headers and Jira/manual notes remain unchanged.
- **Verified synthetically:** 100/500/1000 representative fake Jira items, exact filter/order results, cache invalidation on manual save/import/error/restart/second Desk process, concurrent reads. Python and Node benchmarks p50/p95 run as smoke in CI. **No fake Windows/real browser timings.**
- **Open QA-09/PERF-05/07 gates:** measure Chrome/Edge DOM scripting/layout/paint, focus/accessibility and 8-hour memory; consider true windowing only when traces show a real bottleneck.
- **Source:** `docs/LARGE_QUEUE_PERFORMANCE.md` records commands, acceptance and limitations.

## 4. Definition of Done для кожного наступного блоку

- Code + focused synthetic tests + privacy test; no new UI modes.
- Only selected supplier involved; no mixed files or PII in public reports.
- Evidence/proof/assumption/unknown are distinct, no root-cause certainty inferred solely from observed failure.
- Human-supplied notes and email drafts preserved; Jira/Confluence read-only and mail never sent.
- CI passes on the PR head **and** post-merge on `main`; user gets exact PR / CI links and real-UAT limits.
- Roadmap statuses/next block updated in this file.

## 5. Інтеграційні обмеження, які потрібно пам'ятати

- GitHub містить код, не корпоративні ZIP, приватні Jira сесії чи OAuth tokens. Сам merge не оновлює локальну Codex automation чи комп'ютер.
- Кількість 30 стосується **прикладів конкретної помилки**, не 30 випадкових перших ZIP; відбір і representativeness має бути зафіксовано.
- Живий Kibana browser/CCON download в локальному Codex є окремою дією; Python offline group analytics обробляє **лише вже реально отримані локальні докази**, не симулює мережевий доступ.
- Плани старих `docs/BA_PRODUCT_REQUIREMENTS.md` і `docs/BA_DESK_VNEXT_REQUIREMENTS.md` можуть містити історичні статуси PR; цей файл має пріоритет у функціональному backlog.
