# CCON BA Desk · продуктовий UX/UI та workflow-аудит (2026-10-25)

**Аудиторська роль:** Product Manager + Staff UX/Frontend/Performance reviewer. **Основний користувач:** один BA, великий особистий backlog, багато постачальників, обмежений час. **Статус:** експертний аудит вихідного коду, **без** інтерв'ю, скринкастів, Browser DevTools замірів та реального UAT. Оцінки нижче є гіпотезами, не заміряними метриками. Джерело пріоритетних продуктних інваріантів: `docs/PRODUCT_BACKLOG.md`.

## 1. Що саме оптимізуємо

> **Не кількість кліків і не красивість.** Максимізуємо кількість *коректно завершених* BA-дій за доступний час, мінімізуючи повернення до задачі, втрату контексту, невірні пріоритети й ризик відправити помилкові вимоги/листи.

**North Star:** confirmed useful task outcomes / 60 хв роботи, *із* quality gate та без прихованої частки переробок. Паралельно: time-to-next-action (TTNA), time-to-safe-handoff (TTSH), minutes-to-resume-after-interruption (MRI), share of wasted context switching, interruption recovery success, unresolved blockers, false-ready outputs.

**Перший екран має відповідати за 3–5 секунд:** (1) Що зараз найкорисніше? (2) Чому саме ця задача? (3) Що конкретно зробити? (4) Чи підготовлено текст/лист/доказ? (5) Чи можна безпечно віддати далі? Чим більше виведено нерелевантного тексту, тим більше часу BA витрачає на пошук відповіді.

**Робочі патерни (не додаткові UI modes):**
- **Triage 10–30 с:** відкрити наступну задачу, побачити дію + потрібне рішення, класифікувати як готове до передачі / потребує дослідження / очікуємо / відкладено, не гублячи статус.
- **Small task 1–5 хв:** скористатися перевіреним готовим Jira-описом чи чернеткою, скопіювати, *вручну* виконати зовнішню дію, зафіксувати факт і перейти далі.
- **Medium 5–20 хв:** 1–3 питання, одна перевірка протоколу або тесту; створити точний acceptance, віддати в роботу або зафіксувати зовнішній блокер.
- **Deep work 20–90 хв:** готовий 30-sec briefing, підтверджені правила, історія рішень, multi-flow докази, альтернативи, QA, повернення після перерви в ту ж позицію/секцію.
- **Batch outbound:** кілька листів для різних постачальників лише після перевірки адресатів/ZIP/методів, без auto-send.
- **Waiting sweep:** мінімум часу на WAIT; наступна дата перевірки й власник відповіді, уникнути повторних листів/аналізу.
- **Urgent interruption:** нова активна sprint-блокуюча задача піднімається нагору; чернетка поточної роботи не зникає; при поверненні видно старий стан.

## 2. Перевірений факт з коду → вплив → рекомендована зміна

| Код / спостереження | Наслідок для швидкості/ризику | Запропоноване рішення |
|---|---|---|
| `assets/task-rules.mjs`: перевірений active sprint поперед backlog, у lane WRITE/READY/DECIDE/REVIEW/WAIT | Формально зберігається пріоритет, але **немає явної оцінки тривалості й ціни перемикання** | Effort + 2-minute candidate тільки **в межах поточної lane і після реального needsEmail**, не ламати sprint контракт |
| `assets/dashboard.mjs`: список із пріоритетом + повна права картка; звичайний інтерфейс користувача | Гарний фундамент. Повна картка дає зайву щільність для 2-хвилинної дії | Progressive disclosure **в існуючих details**, коротка дія/готовий артефакт завжди видимі |
| `saveTask(done=true)`: зберегти і перейти до наступної | Прискорює потік, але Done до зовнішньої передачі може хибно означати завершення | Окреме явне підтвердження handoff / ручний статус, без авто-оновлення Jira |
| `captureForm` зберігає локальний recovery state, `beforeunload` попереджає | Добре проти випадкової втрати вводу | Показувати unsaved/saving/saved/failure, конфлікти ревізій; тести на multi-tab і рестарт |
| `saveStatus`: статус надсилається окремо від нотаток/листа | Статус зберігається без випадкового перезапису письмової чернетки | Перевірити race між статусом і повним save, retry та error consistency |
| `dashboard.mjs`: 5-секундний повний task fetch + 5-секундний logs/report/health | Зайве навантаження SQLite, мережі, JSON.parse, `JSON.stringify`, особливо у великому backlog | Легкий revision endpoint; пропуск повного fetch без змін; прихована вкладка зупиняє роботу |
| `filterTasks`: склеює full description, правила, залежності на кожен фільтр | Витрати CPU при кожній клавіші пошуку | Ранній cheap-filter/no-query exit, далі debounced search і стабільний індекс |
| `renderList`: innerHTML усього списку та per-row listeners | 500+ рядків можуть створювати ривки, зсув фокуса і scroll | Event delegation, віртуалізація лише після реального profiling, доступна навігація |
| `renderDetail`: повторний HTML всієї великої картки | Відкриті details/scroll можуть скидатися при оновленні | Утримувати expanded state/scroll/selection, ререндер лише змінених секцій |
| `taskVersion` і зберігання локальних форм | Є basic race avoidance, але зміни в іншій вкладці не мають явного merge-контракту | Revision/ETag + conflict banner + reject stale save, тести без втрати user edits |
| `desk_store.py`: кожен `view()` JSON-декодує усі tasks | Повний експорт завжди дорогий, навіть коли нічого не змінилось | Спочатку cheap revision, потім профілювання cache/pagination лише за необхідності |
| `server.py`: приватний localhost + строгі headers; запуск без build | Правильна мала залежність, короткий старт | SLO на start/respond/recover, підтримка Windows, zero-cloud telemetry by default |
| `evaluation.py`: 20–30 frozen cases + human rubric; `ba_quality_gate` | Схема фактичної якості вже існує, але human verdict ще відсутній | Фіксувати Task Quality та Effort/time separately; blinded baseline/candidate |
| Джерела Jira/Confluence/PDF hash-verified local | Менше вигаданих доказів, але все ще локальні браузерні дії | Доказові кнопки показувати за ready/stale/blocked, не симулювати повноту |
| `dashboard.html`: локальна основна картка / сортування / пошук, без окремих режимів | Стабільний ментальний макет | Поступове вдосконалення **без нового sidebar/tab/Quick-vs-Deep режиму** |
| `assets/dashboard.css`: великий stylesheet, базовий focus-visible | Можливий drift та проблеми контрасту/zoom/вузьких екранів | Keyboard/200%-zoom/screen reader/forced colors audit; CSS cleanup за visual diff |

## 3. Продуктова модель пріоритетів: не плутати важливість і «швидкість закриття»

**Незмінні hard constraints:**
1. Тільки мої Jira issues, не чужі linked tickets в черзі.
2. Усі підтверджені active sprint tasks перед будь-яким backlog.
3. Усередині sprint/backlog **справжній WRITE/needsEmail** перед іншими сигналами, не кожна optional email draft.
4. Потім сигнал/ризик, чинний queueScore (0–100), blocking та ручні стани. DONE, WAIT, stale, відсутній proof не маскувати під READY.
5. **Effort/time не може тихо переставити** sprint vs backlog чи поставити необґрунтовану 2-хвилинну задачу вище blocking 90-point ticket.

**Додати незалежну EffortEstimate:** XS 0–2 хв, S 2–5, M 5–20, L 20–60, XL 60+ або UNKNOWN. Це людське/підтверджене поле, а не AI-«факт»; вказувати confidence і причину. Зберігати original priority score і high-risk blocker. Видиме позначення effort лише після UAT. Додати відношення `expectedUnblockImpact / effort` як *допоміжну* підказку серед задач з однаковим hard priority, не прихований re-score.

**Локальна тактика:** 5-хвилинний ранковий triage → 20–40 хв batch confirmed quick handoffs → 60–90 хв одна пріоритетна deep task → 5–10 хв waiting follow-up. Це тестована робоча гіпотеза, не жорстке правило розкладу; критичний blocking sprint ticket перериває batch.

**Anti-patterns:**
- «Закривати дрібне заради числа Done» ⇒ пропуск великих критичних інтеграційних багів.
- Автоматичне Done після Copy/Mailto ⇒ у Jira або пошті жодна дія ще не доведена.
- Автоматично вважати `STRUCTURALLY_VERIFIED` бізнес-згодою ⇒ невірні вимоги.
- Переносити на початок усе з чернеткою листа ⇒ необґрунтоване WRITE.
- Автоматична зміна ранжування після ручної зміни status під час редагування ⇒ втрата фокуса.
- Голі vanity metrics, KPI «завершено сьогодні» без повторної роботи, scope, якості та duration.

## 4. Пріоритетна information architecture для існуючої сторінки

**Зона списку (сліва):** номер і Jira key; однорядкова читабельна назва; *одна* найближча дія, тривалість тільки підтверджена, сигнал + score + sprint + блокер; без 5 одночасних чіпів. Групи sprint/backlog/wait/done збережені. Для довгих черг sticky search, лічильники груп, keyboard first. Ніякого нової вкладки чи «Quick Mode».

**Зона деталі (справа, above-the-fold):** що зробити зараз → готовий артефакт для копіювання/редагування → що саме потрібно перевірити перед handoff → стан джерел. Простий *job-to-be-done* шлях: Read → Verify → Copy/Send Manually → Record → Next. Не ставити історію/ZIP/QA-матрицю до actionable line; вони в наявних згорнутих секціях.

**Для складної задачі:** 30-sec briefing і current/target; підтверджена IF/THEN; джерела; альтернативи; explicit missing info; acceptance checks; open questions; log versions. Зберігати останню відкриту секцію і позицію для повернення після interruption. Немає синтетичних «confirmed» полів.

**Мікровзаємодії:** явний copy feedback, atomic save, clear stale warning, reversible mark DONE, не змінювати selection на фоні, не закривати mailto автоматично. Підсвічування ключових невирішених полів без кольору як єдиного носія інформації. Стан «немає даних» відрізняти від «помилка читання».

## 5. Модель вимірювання (baseline ще НЕ виміряний)

| KPI | Визначення | Орієнтовний initial target для UAT, не факт |
|---|---|---|
| TTNA p50 / p95 | Від вибору задачі до розуміння першої необхідної дії | ≤ 10 с / ≤ 25 с |
| Quick-task TTSH p50 / p95 | Від вибору готового S до явної ручної передачі та фіксації | ≤ 90 с / ≤ 4 хв |
| Resume time p50 / p95 | Після перемикання назад до визначеної наступної дії | ≤ 15 с / ≤ 45 с |
| Completion with factual integrity | Частка handoff без хибної вимоги / вигаданого доказу | 0 critical false claims, gold human review |
| Keyboard task transitions | Для типового flow від вибору до Next без миші | ≤ 5 intentional actions для already-ready case |
| Loaded task cache stability | Full `/api/tasks` calls коли revision незмінна | 0 додаткових full-fetch після першого успішного load |
| Local API median / p95 | `/api/tasks/revision` vs `/api/tasks` on synthetic 100/500/1000 | Визначити з замірів, не закладати CI time threshold |
| DB data integrity | Unexpected shutdown, concurrent writes, restart, malformed snapshot | 0 втрачених підтверджених локальних edits |
| UI accessibility | Keyboard, tab order, screen reader, 200% zoom, narrow viewport | 0 blocking issues у критичних діях |
| Perceived speed | Перша видима usable queue і detail після старту | p95 < 2 с на контрольному ноутбуці (target) |

**Як тестувати:** мінімум 5 експертних сценаріїв × repeated attempts: urgent sprint, 3 independent quick handoffs, supplier WRITE з ZIP і ручним email, WAIT з follow-up, multi-error deep work after interruption. Знімати time, clicks, unnecessary scroll, failed recovery, error rate; окремо протестувати 100/500/1000 синтетичних задач. Не використовувати реальні Jira payloads у публічних тестах.

## 6. UX/UI експертні ризики: 12 зон оцінювання

| Зона | Аудиторське питання | Ризик/наступний тест |
|---|---|---|
| Information scent | Чи видно дію, розмір задачі та доказ, не відкриваючи 5 деталей? | Card focus, truncation/contrast/labels |
| Cognitive load | Чи вмістити current/target/next/QA без дублювання? | 5-second comprehension study |
| Interruptions | Чи повертається edit cursor, scroll та open section після 10 хв? | Multi-task context restore |
| Navigation | Search, jumps, Next, Back, queue position | Keyboard + 100/500 queue |
| Error prevention | Чи не може помилковий ZIP/method піти в mail draft? | Quality Gate UAT |
| Readiness honesty | Copy ≠ sent; linked ≠ read; prepared ≠ approved | Readiness microcopy |
| Sorting trust | Sprint / WRITE / score / block причини зрозумілі | Show ranking rationale |
| Data freshness | Який snapshot, чи stale, чи сервер працює? | 3-second failure/recovery |
| Trust in drafts | Лише source-grounded text, edit safe | Human proof / source audit |
| Accessibility | Focus order, keyboard escape, dialog semantics, zoom | WCAG 2.2 AA audit target |
| Responsiveness | Split layout at narrow/medium/large | 320/768/1440px + 200% zoom |
| Reliability | Дві вкладки, відключення живлення, corrupt JSON, revision races | Recovery + atomic save tests |

## 7. Decision record і межі

- **Не робимо зараз:** повний редизайн; modes Quick/Deep/Email; автоматичну відправку листів; автоматичний Jira write; хмарний product analytics, telemetry або перенесення PII в GitHub.
- **Робимо зараз:** зберігаємо структуру, прибираємо зайвий poll/обробку, документуємо measured-first SLO, покриваємо статус/DB/HTTP regressions.
- **Після базових замірів:** effort hints, keyboard, one-click handoff checklist, focus persistence, optimized large list rendering, instrumentation local-only.
- **Людське UAT** є обов'язковим для зміни сортування, semantics Done, email send-ready і «скорочення» технічних текстів. Автоматизація може допомагати, але не має тихо вирішувати за BA.
