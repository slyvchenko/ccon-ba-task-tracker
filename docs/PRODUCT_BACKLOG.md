# CCON BA Desk — єдиний реєстр можливостей і backlog

**Версія реєстру:** 2026-10-25 · **джерело правди:** `docs/PRODUCT_BACKLOG.md` · **власник:** один BA, лише його Jira-задачі.  
**Базовий код:** `main` після злиття PR #18 (v2.18). **Поточний кандидат:** PR #19 (v2.19), human-UAT після зеленого CI.  
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
10. **Жоден великий PR:** рухатись блоками по 2–3 пов'язані можливості, синтетичні й реальні acceptance cases, зелений CI до merge; після merge перевіряти також CI на `main`.

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
| BA-01 | P0 | PARTIAL (description quality checks); expert UAT open | Готовий короткий англомовний task description | Кожна умова IF/THEN, field, expected output, QA зчитані коректно; human gold set |
| BA-02 | P0 | PARTIAL | Готовий фактологічний emailDraft для **кожної** задачі | Незалежно від WRITE; не вигадувати адресата/метод/прикріплений ZIP; коректний follow-up |
| BA-03 | P0 | IMPLEMENTED (code) | 30-second context: confirmed/current/target/action/why | Зрозумілий стислий briefing із proof/uncertainty |
| BA-04 | P0 | IMPLEMENTED (mechanical excerpt gate); semantic UAT open | Source-grounded facts vs interpretations vs assumptions | Для кожного важливого твердження source offset/URL і support test |
| BA-05 | P0 | PARTIAL | BA questions ID, status, owner, answer, evidence | OPEN → ANSWERED / SUPERSEDED / NOT_APPLICABLE; пропажа з AI ≠ answered |
| BA-06 | P1 | IMPLEMENTED (new-comment candidates); semantic UAT pending | Розпізнавання реальної відповіді на питання з Jira/документів | Запропонувати кандидата відповіді з цитатою; без auto-close |
| BA-07 | P0 | IMPLEMENTED (explicit rule/QA references); real-case UAT open | Requirement → QA traceability | Зіставити позитивні/негативні/edge-cases із кожною підтвердженою вимогою |
| BA-08 | P1 | IMPLEMENTED (approved-model single-task CLI); live UAT open | On-demand deep re-analysis однієї задачі | Перезапуск без повного щоденного проходу, повага до збережених ручних правок |
| BA-09 | P1 | PARTIAL | Related Jira + wiki/documentation cross-check | Читати доступні джерела, фіксувати непрочитані та конфлікти |
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
| EVD-13 | P1 | PARTIAL (v2.21 local JSON/XML/ZIP structure; PDF text & Confluence unread, live UAT open) | Вкладення Jira (PDF/JSON/XML/ZIP), Confluence/wiki | Read-only extraction, не просто метадані; bounded/safe parser, source audit |
| EVD-14 | P2 | PARTIAL (distinct-flow recurrence, no historical prevalence) | Cross-case anomaly detection: recurring errors across time | Порівняння case signatures з попереднім аналізом без PII |
| EVD-15 | P2 | PLANNED | Кероване зберігання raw ZIP: retention, cleanup, quota | Encrypt-at-rest/ACL, TTL, аудит, no commit/no egress |
| OUT-01 | P0 | PARTIAL | Самодостатній BA dossier із короткою дією, правилами, QA, gaps | Реальні приклади без зайвих формулювань; scenario-based grading |
| OUT-02 | P0 | PARTIAL | Чернетка листа, subject/method, контекст попередніх відповідей | Ситуативне формулювання, ручне редагування, без auto-send |
| OUT-03 | P1 | IMPLEMENTED (code); live UAT pending | Готовий supplier ZIP та evidence status без прихованої недоступності | Показувати ready/stale/blocked + причина і flow у поточній картці |
| OUT-04 | P1 | IMPLEMENTED (claim/source gate); semantic UAT open | Контроль фактичності вставлених доказів і PDF/логів | Кожна вимога та тест мають джерело, або чітко OPEN |
| UX-01 | P0 | IMPLEMENTED (code) | Зберігати стандартну сторінку, без окремих режимів | Меню/поля/status/email/лог ZIP збережені |
| UX-02 | P1 | PARTIAL | Compact descriptions і progressive disclosure | Скорочення повторів, не ховати основний результат |
| UX-03 | P2 | PARTIAL | AERTiCKET-inspired branding | Дійсні токени/логотип потребують brand approval |
| UX-04 | P2 | IMPLEMENTED (copy/edit mail, next/save); live UAT open | Copy task/email + quick next/open/save | Можливість проходити список без зайвих кліків, UAT |
| QA-01 | P0 | IMPLEMENTED (code) | Python/Node/Release/Compose CI | Required checks + merge only when green |
| QA-02 | P0 | GATE | Live Jira + Kibana + CCON auth UAT з 2–3 реальними задачами | Browser session, 1 normal flow, 1 multi-error flow, 1 ambiguous flow |
| QA-03 | P0 | GATE (frozen 20–30 real-case workflow implemented, scores not yet collected) | Реальні 20–30 gold cases, blinded AI vs analyst | Measure false facts, missed conditions, task/edit quality |
| QA-04 | P1 | PARTIAL | AI quality metrics, reject invalid dossier | Structured schema / briefing/factors checks implemented; factual support pending |
| QA-05 | P1 | PARTIAL | Safe daily prompt calibration checklist | Whitelisted diagnostics implemented; prompt version change evaluated separately |
| QA-06 | P1 | IMPLEMENTED (staged A/B + human approval + rollback); real reviews pending | Prompt A/B regression / automatic candidate proposal | Human gate, compare gold set, rollback, no unreviewed auto-prompts |
| QA-07 | P2 | PLANNED | Offline fixtures for realistic REST/XML/multi-error formats | Coverage by supplier method, nested ZIP cases, pagination, retries |
| QA-08 | P1 | PARTIAL (v2.20 model egress sanitizer and synthetic regressions; full DLP/log audit pending) | Data minimization/security for prompt, manifests, debug logs | PII/credentials, safe link stripping, prompt injection regression |
| INF-01 | P3 | DEFERRED | Cloud deployment: SSO/OIDC/HTTPS/hosting | Cloud pilot code exists, real infra and security approval not started |
| INF-02 | P3 | DEFERRED | Backups, PostgreSQL, multi-worker safety, operations alerts | After local feature quality/infra approval |
| INF-03 | P3 | DEFERRED | Real unattended scheduling and live model setup | Does not block local Codex project |
| INF-04 | P3 | DEFERRED | Formal secrets manager, brand/legal approvals | Production security gate |

## 3. Рекомендовані невеликі PR / порядок

| Блок | Обсяг (не більше 2–3 функцій) | Гейт |
|---|---|---|
| **#9 — CODE COMPLETE; LIVE UAT OPEN** | EVD-07: 1–30 error cases з локально підготовлених flow reports; EVD-08: evidence-based RCA із альтернативами й прогалинами | Synthetic multi-flow regression + flow/supplier isolation + baseline CI. Реальний Kibana UAT окремо |
| **#10 — CODE COMPLETE; LIVE BROWSER UAT OPEN** | EVD-05: локальний browser-to-ZIP handoff із журналом помилок; OUT-03: ready/stale/blocked ZIP в existing card | Реальний авторизований download без cookies/API leaks |
| **#11 — CODE COMPLETE; HUMAN CONTENT UAT OPEN** | BA-04 + OUT-04: перевірка зв'язку claim→source; BA-07: QA traceability | Невідтворювана вимога залишається OPEN |
| **#12 — CODE COMPLETE; LIVE UAT OPEN** | BA-06: question answer suggestions; BA-10: decision register | Не закривати питання автоматично |
| **#13 — CODE COMPLETE; LIVE UAT OPEN** | EVD-09/EVD-11: mapping contracts + flow timeline | Два request paths, retry/timeout, ordering |
| **#14 — CODE COMPLETE; LOCAL UAT OPEN** | CORE-07/CORE-08: history + personal action plan | Один екран, current vs previous, overdue |
| **#15 — CODE COMPLETE; LIVE UAT OPEN** | BA-08/UX-04: one-task reanalyze + copy workflow | User edits untouched |
| **#16 — CODE COMPLETE; REAL GOLD-SET UAT OPEN** | QA-03/QA-06: frozen gold-set + human-approved prompt A/B | No critical false claims |\n| **#17–18 — CODE COMPLETE; LIVE UAT OPEN** | EVD-10/12/14 (частково), CORE-09, BA-11 | Перевірка реальних Jira/Kibana даних |\n| **#19 — MERGED; HUMAN UAT OPEN** | CORE-10: щоденний score delta, зміни факторів, пояснювальні попередження | CI green, без auto-ranking |\n| **#20 — MERGED; SECURITY UAT OPEN** | QA-08: безпечна мінімізація даних перед відправленням у схвалену модель | Synthetic prompt payload, URL/PII/secrets tests + CI |\n| **#21 — IN PROGRESS** | EVD-13: локальний браузерний handoff JSON/XML/ZIP, прив'язка доказів до Jira fingerprint | ZIP safety, structure only, PDF explicitly unread |
| **Далі** | EVD-13b (PDF/wiki extraction after approved parser), EVD-15 (ZIP retention), UX-02/QA-07 | Окремі невеликі PR після перевірки попереднього |
| **Пізніше** | INF-01..04 (cloud/production) | Свідомо поза поточним scope |

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
