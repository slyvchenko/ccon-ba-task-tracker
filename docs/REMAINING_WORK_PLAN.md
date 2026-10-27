# CCON BA Desk: реєстр усієї незавершеної роботи після v2.48.1

**Джерело:** `docs/BACKLOG_ACCEPTANCE_LEDGER.json` з `docs/PRODUCT_BACKLOG.md`. **План, не факт виконання.** Реальні Jira/CCON/Kibana й людське BA-приймання не можна закрити синтетичним CI.

**В інвентарі:** 129 вимог; 40 з code-reported IMPLEMENTED (також без human acceptance); **89 залишилися відкритими для реалізації, перевірки, scope-рішення або UAT**.

## Порядок реалізації

1. Спершу P0 real source / 26-case QA / privacy gates: жодного false-ready чи непідтвердженого XML/PNR/mapping.
2. Далі P1 функції, які скорочують час BA без зміни hard sprint/WRITE lanes і без автоматичного Jira/email write.
3. Потім P2: лише після перевірки дублювання (16 VIS), користі та UX, щоб не множити вкладки, dashboards і шаблони.
4. P3 cloud/SSO/PostgreSQL не входить до локального релізу без окремого рішення.

## Інвентар відкритих робіт

### Приватне BA/Windows приймання (4)

| ID | P | Стан | Дія / рішення | Критерій виконання |
|---|---|---|---|---|
| QA-02 | P0 | GATE | Виконати незалежне приватне приймання за DoD. | Browser session, 1 normal flow, 1 multi-error flow, 1 ambiguous flow |
| QA-03 | P0 | GATE | Виконати незалежне приватне приймання за DoD. | Measure false facts, missed conditions, task/edit quality |
| QA-10 | P0 | GATE | Виконати незалежне приватне приймання за DoD. | TTNA/TTSH/MRI with 0 critical false-ready decisions |
| QA-13 | P1 | PARTIAL | Виконати незалежне приватне приймання за DoD. | Actual independent gold scores, not CI counts |

### Критичні P0 докази та достовірність (18)

| ID | P | Стан | Дія / рішення | Критерій виконання |
|---|---|---|---|---|
| BA-01 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Кожна умова IF/THEN, field, expected output, QA зчитані коректно; human gold set |
| BA-02 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Незалежно від WRITE; не вигадувати адресата/метод/прикріплений ZIP; коректний follow-up |
| BA-05 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | OPEN → ANSWERED / SUPERSEDED / NOT_APPLICABLE; пропажа з AI ≠ answered |
| EVD-03 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Позначати `CANDIDATE_ONLY`; підтверджувати transformation rule проти специфікації |
| EVD-06 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Action plan вже є; потрібні локальні браузерні перевірки |
| OUT-01 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Реальні приклади без зайвих формулювань; scenario-based grading |
| OUT-02 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Ситуативне формулювання, ручне редагування, без auto-send |
| QUICK-02 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | ≤5 intentional actions; zero Jira write; J-03/J-08 |
| QUICK-03 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Human confirmation and timestamp; no fabricated delivery proof |
| FOCUS-01 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No jump on background import, user edits preserved; J-07 |
| FOCUS-02 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Resume p95 goal ≤45 s; browser UAT |
| PRIOR-01 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Human-reviewed or source-derived; never business truth guess |
| PRIOR-02 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Ranking reason for 100% selected tasks; J-02 |
| PRIOR-03 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Property-based synthetic test set, no cross-lane promotion |
| REL-02 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Forced close/reopen/reload leaves acknowledged edits intact |
| REL-03 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Crash drill, documented recovery and permissions |
| QA-11 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | P-15/P-17/P-18, 0 silent overwrite |
| SEC-01 | P0 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No CSRF/security relaxation |

### P1 робочий процес, безпека і надійність (39)

| ID | P | Стан | Дія / рішення | Критерій виконання |
|---|---|---|---|---|
| BA-09 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Читати доступні джерела, фіксувати непрочитані та конфлікти |
| EVD-10 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Bad request, provider reject, mapping, timeout, CCON internal із підтвердженим stage |
| EVD-13 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Read-only extraction, не просто метадані; bounded/safe parser, source audit |
| OUT-04 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Кожна вимога та тест мають джерело, або чітко OPEN |
| UX-02 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Скорочення повторів, не ховати основний результат |
| QA-04 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Structured schema / briefing/factors checks implemented; factual support pending |
| QA-05 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Whitelisted diagnostics implemented; prompt version change evaluated separately |
| QA-08 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | PII/credentials, safe link stripping, prompt injection regression |
| QUICK-04 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. Перевірити перетин: BA-02, OUT-02. | No false ready for missing ZIP/method/recipient; J-04 |
| QUICK-05 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Sprint/WRITE contract unchanged; reordering by time opt-in only |
| QUICK-07 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. Перевірити перетин: VIS-01, VIS-04. | User 5-second scan, no loss of proof status |
| FOCUS-03 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Keyboard-only critical path A-01; no destructive collision |
| FOCUS-04 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No extra tabs/modes; J-03/J-06 |
| FOCUS-05 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No page redesign; responsive A-03/A-04 |
| FOCUS-06 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No focus loss, cursor jump, stale overwrite |
| PRIOR-04 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Time benefit cannot overtake urgent sprint/blocker |
| PRIOR-05 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Explainable, human acceptance > 90% ordering confidence |
| PRIOR-06 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Due status visible, source-backed, J-05 |
| UI-05 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. Перевірити перетин: VIS-04, VIS-15. | A-03; no horizontal overflow/hidden primary action |
| UI-06 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | A-07/A-12 and race tests |
| UI-07 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Correct recovery action in each state |
| PERF-05 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No focus/aria regression; compare 500/1000 |
| PERF-07 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Named Windows machine p50/p95, memory trend |
| PERF-08 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Fetch selected only on selection/revision, compare versions |
| REL-04 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No error swallowed; error state shown, P-12 |
| REL-05 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No database damage/partial save, Windows UAT |
| REL-06 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | v2.23→current, old DB revision initialized once |
| REL-07 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No duplicate mailto or Done, bounded retry |
| REL-08 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Fail closed/notice for insecure ACL configuration |
| A11Y-01 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | A-01/J-03/J-08 with focus protection |
| A11Y-02 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | A-03/A-04; primary actions reachable |
| A11Y-03 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | A-02, announcements not noisy |
| A11Y-04 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | A-11; no unintended send |
| QA-12 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Focus, click, screenreader, history, network reconnect |
| QA-14 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No invented 100%; dev-only tooling approval |
| OPS-02 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | No production logs by default; explicit export |
| OPS-03 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Main merge does not update installed local copy |
| SEC-02 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Host restrictions and current OIDC origin untouched |
| SEC-03 | P1 | PARTIAL | Закрити відсутню частину DoD кодом/тестом або приватним UAT. | Synthetic samples only; cross-check on PR |

### P2 експерименти та можливе спрощення (24)

| ID | P | Стан | Дія / рішення | Критерій виконання |
|---|---|---|---|---|
| CORE-10 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Виявляти великі зміни без нового Jira fingerprint; AI bias не доведено автоматично |
| EVD-14 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Порівняння case signatures з попереднім аналізом без PII |
| EVD-15 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Encrypt-at-rest/ACL, TTL, аудит, no commit/no egress |
| UX-03 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Дійсні токени/логотип потребують brand approval |
| QA-07 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Coverage by supplier method, nested ZIP cases, pagination, retries |
| QUICK-08 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Template never invents source/method; gold QA |
| FOCUS-07 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Manual pin only within lane; clear override and reset |
| FOCUS-08 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | A-01/A-11; action accessible |
| PRIOR-07 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Local opt-in, no PII, no cloud telemetry |
| PRIOR-08 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Never silently retrain queue ranking; human UAT |
| PRIOR-09 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Not a gamified Done count, J-01 |
| UI-08 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | No truncation in clipboard/export, A-06 |
| UI-09 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. Перевірити перетин: VIS-06, VIS-10. | Keep main results visible, never bury next action |
| UI-10 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. Перевірити перетин: VIS-15. | Snapshot on 3 viewport sizes; no brand approval bypass |
| PERF-09 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. Перевірити перетин: VIS-15. | No unexpected fonts/spacing/contrast changes |
| PERF-10 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Do not enable blindly; Windows/backup compatibility |
| REL-09 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | No unexpected data deletion, archive user-approved |
| REL-10 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Verify hashes; old app loads additive migration |
| A11Y-05 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | A-05/A-10 |
| A11Y-06 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. Перевірити перетин: VIS-14. | A-09 and touch accuracy |
| QA-15 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | OS, Python version, locale, browser, power mode |
| OPS-04 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | No remote telemetry or background transfer |
| OPS-05 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | Speed and accurate stale flags |
| SEC-04 | P2 | PARTIAL | Спершу usage/overlap review; потім build або явно defer. | No stale PII in unsafe storage without retention policy |

### P3 хмарний продукт лише за окремим рішенням (4)

| ID | P | Стан | Дія / рішення | Критерій виконання |
|---|---|---|---|---|
| INF-01 | P3 | DEFERRED | Не реалізовувати у локальному scope без product approval. | Cloud pilot code exists, real infra and security approval not started |
| INF-02 | P3 | DEFERRED | Не реалізовувати у локальному scope без product approval. | After local feature quality/infra approval |
| INF-03 | P3 | DEFERRED | Не реалізовувати у локальному scope без product approval. | Does not block local Codex project |
| INF-04 | P3 | DEFERRED | Не реалізовувати у локальному scope без product approval. | Production security gate |

## Правила приймання і закриття

- Усі `human_acceptance` залишаються `NOT_RECORDED`; GitHub PR та CI не є бізнес-узгодженням.
- Для кожного P0/P1 зазначити реалізацію, тести, source proof і залишкові UAT-gates; не ставити DONE за існування файла.
- Для P2/P3 - явне product рішення KEEP / CONSOLIDATE / DEFER / DROP з обґрунтуванням, без автоматичного видалення вимог.
- Реальні дані, скриншоти з Jira, supplier ZIP, token, PNR та приватний QA-звіт не вивантажувати до публічного репозиторію.
- Пов'язаний live-acceptance blocker: GitHub Issue #50.
