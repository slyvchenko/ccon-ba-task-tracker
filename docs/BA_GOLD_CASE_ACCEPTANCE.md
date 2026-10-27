# BA Desk: перевірка 20–30 реальних задач перед випуском

**Версія:** v2.39, 26.10.2026. **Статус:** шаблон приймання; жодного реального бізнес-кейсу не оцінено цим PR. Для завантаження фактів і приватних кейсів використовуй тільки затверджене локальне середовище. Не коміть Jira/PNR, supplier REST/XML/ZIP, email-адреси, токени, cookies чи скриншоти з реальними даними.

## Вибірка та методика

Рекомендована когорта **26 приватних BA-кейсів**, мінімум 20, максимум 30. Набір має бути заморожено до порівняння. Усі кейси аналізуються однаковою версією prompt/model, з фіксованими правилами QA і source access. Аналітик пише незалежну очікувану відповідь до перегляду результату AI; оцінює інший рецензент, або перший рецензент робить blind review з окремим ключем відповідей.

| Архетип | Рекомендовано | Обов'язкові перевірки |
|---|---:|---|
| READY / короткий однозначний task | 4 | Наступна дія, 5-секундне розуміння, 0 зайвих кликів |
| WRITE / supplier email + ручний handoff | 5 | Адресат тільки підтверджений, subject, метод, ZIP тільки supplier XML, без твердження «лист надіслано» |
| WAIT / dependent decision | 4 | Хто і на що чекає, дата, без повторного листа та false DONE |
| DECIDE / суперечливі правила | 4 | AND/OR, expected result, enum/field literal, точне відділення факту від припущення |
| Deep NDC, rebooking, multi-city | 5 | Точні journey/segment/status/field refs; правила grouping не виводяться із кореляції |
| Повторні supplier/API помилки | 4 | Репрезентативні flows, missing evidence, counterexample, no false root cause |
| **Разом** | **26** | 5+ типів роботи; multi-step і edge-case покриття |

Допускається змінювати кількість у групах, не виключаючи жоден архетип. Критичний baseline перед експериментом: заміряти кількість кліків/розкриттів, час до правильної наступної дії (TTNA), час до придатної чернетки (TTSH), відсоток помилкової передачі і пропущених важливих умов. **3–5 секунд** для простих задач є продуктовою гіпотезою, а не результатом поточного CI.

## Протокол на один кейс (лише приватно)

| Поле | Що фіксувати |
|---|---|
| Case ID | `GOLD-01`... `GOLD-30`, без реального PNR у публічному репозиторії |
| Архетип і підзадачі | READY / WRITE / WAIT / DECIDE / DEEP / ERROR; які саме умови тестувалися |
| Джерела | Jira, Confluence, Kibana, CCON REST, supplier XML, локальні вкладення; які джерела недоступні |
| Analyst expected | Готовий Jira task, exact field/enum, AND/OR, supplier mail draft, QA positive/negative/edge |
| AI observed | Лише у приватному сховищі, з version/model, часовою міткою й підтвердженою source revision |
| Proof review | PASS / FAIL / INCONCLUSIVE для facts, flow mapping, rule logic, attachments, owner/recipient |
| Safety review | Не було Jira write, auto-send, false ready, false source, ризику витоку |
| Speed and UX | TTNA, TTSH, клики, scroll/expand, фокус/видимість блокерів |
| Human reviewer | Ким, коли й у якому приватному артефакті схвалено |
| Result | **PASSED / FAILED / BLOCKED**; конкретний дефект і PR owner |

Не зберігай ідентифікаційні дані рецензента або корпоративні секрети у публічному CI. Для GitHub використовуй **лише агрегати** та reference на внутрішнє захищене сховище без приватного URL/ключа.

## Blocking acceptance gates

1. **QA-02:** авторизована реальна Jira/Kibana/CCON сесія, normal flow, multi-error і ambiguous flow. Відсутність доступу = **BLOCKED**, а не PASS.
2. **QA-03:** 20–30 оцінених випадків з експертним незалежним reference, без invented source/recipient/ZIP. Непідтверджені бізнес-правила мають залишатися OPEN.
3. **QA-10:** 5 BA архетипів спостереження, фактичні TTNA/TTSH і відсутність critical false-ready. Synthetic performance не є людським результатом.
4. **QA-13:** локальна лише приватна вибірка, агрегований підсумок, provenance версій, дефекти маршрутизуються у #40–48.
5. **Windows release:** Windows Chrome/Edge, 200–400% zoom, keyboard/NVDA, локальна SQLite crash/restore й 8-годинний сеанс не можуть бути закриті Linux Chromium synthetic CI.

## Правила схвалення

- P0 safety/accuracy **zero critical false-ready, zero unapproved Jira writes or email sends, zero false ZIP attached or supplier response claims**. Це критерій блокування випуску, а не гарантія, яку можливо довести існуванням unit-тестів.
- При відсутності REST/supplier/schema доказу результат **INCONCLUSIVE/BLOCKED**, не вигаданий PASS.
- Непройдені кейси повертаються в конкретний тематичний PR; тест зберігається без PII і запускається повторно після виправлення.
- Підпис на фінальний release дає людина. `docs/BACKLOG_ACCEPTANCE_LEDGER.json` навмисно містить `human_acceptance=NOT_RECORDED` для всіх 129 рядків, поки ці результати не підтверджено.

## Зв'язок із програмою PR

**#39:** inventory + перевірюваний acceptance ledger і цей протокол. **#40–41:** доказова база і handoff P0. **#42–44:** workflow/priority/RCA. **#45–47:** security/Windows/perf/accessibility. **#48:** реальне схвалення релізу, без автоматичного перетворення blocked UAT у DONE.

Реальний UAT не виконується публічним GitHub Actions: це навмисна межа приватності й авторизації.


## Доповнення v2.50.9: локальний анонімний preflight

`python private_gold_review.py --input <local-private-review.json>` перевіряє структуру 20–30 **вже оцінених людиною** анонімних кейсів і рахує лише агрегати. Деталі JSON та обмеження описані в `docs/PRIVATE_GOLD_REVIEW.md`. Навіть якщо синтетичний набір формально заповнений, результат містить `humanAcceptance=NOT_RECORDED` і `releaseApproved=false`. Сама поява цього скрипта не є доказом доступу до реальних Jira/Kibana/CCON, правильних source mappings чи незалежного підпису.
