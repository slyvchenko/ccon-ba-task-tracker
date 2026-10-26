# CCON BA Desk

Локальний BA dashboard: Python + SQLite, без встановлення додаткових Python пакетів. Дані надходять із Jira або файла Rovo.

## Запуск на Windows

1. Завантаж репозиторій: **Code → Download ZIP**, розпакуй у постійну папку.
2. Двічі клацни **Start CCON BA.bat**. Відкриється http://localhost:8765.
3. Залиш вікно запуску відкритим. Щоб зупинити сервер, натисни Ctrl+C у цьому вікні.

Потрібен Python 3.10+. Скрипт перевіряє `py`, `python`, потім вбудований Python Codex. За потреби створи `.python-path` з повним шляхом до python.exe в одному рядку. Встановлення: https://www.python.org/downloads/windows/.

Альтернатива: `python server.py --open`. Якщо порт зайнятий: `python server.py --port 8766 --open`.

## Перший тест

Скопіюй `examples/snapshot.json` у `inbox/CCON_BA_Snapshot.json`. Це **вигадані DEMO задачі**, не Jira дані. Обери значення у списку «Мій статус» — воно збережеться одразу. Додай нотатку й натисни «Зберегти все». Онови snapshot з новішим `generatedAt` і зміни оцінку Rovo — твій статус та нотатка залишаться.

## Щоденна робота

У Work налаштовано щоденне повернення в цей чат за розкладом наявної automation. Комп'ютер і застосунок Work мають працювати для доступу до локальних файлів. Інструкція агента: `DAILY_REVIEW.md`.

Агент завантажує всі задачі за JQL, усі коментарі й доступні пов'язані задачі, аналізує кожну, оновлює чергу й українські пояснення. Задачі Jira та листування залишаються під твоїм контролем; імпорт зберігає ручні статуси, нотатки й відредаговані чернетки.

1. Відкрий dashboard через **Start CCON BA.bat**.
2. Доступні дії, листи, рішення й перевірки сортуються разом за ризиком та пріоритетом; очікування — нижче. Пошук і фільтр дозволяють побачити весь набір.
3. Обери задачу в черзі ліворуч. У картці прочитай «Чому така оцінка» й «Наступна дія» українською; також доступні відкриті питання та джерела.
4. Список «Мій статус» автоматично зберігає **лише статус** у SQLite. Нотатки й відредаговану чернетку збережи кнопкою «Зберегти все»; перевір повідомлення про успішне збереження.
5. Чернетка листа видима й редагується. Перевір адресата, тему та текст, натисни «Відкрити в пошті» — чернетка збережеться й відкриється в поштовій програмі. Надсилаєш лист ти.
6. «Готово → Далі» зберігає нотатки й чернетку, встановлює статус «Завершено» та обирає наступну задачу з поточного списку.

Для ручного отримання Jira: `python jira_sync.py`. Це завантажує контекст, але **не виконує інтелектуальний аналіз** — його виконує агент Work за `DAILY_REVIEW.md`. Результат аналізу застосовується командою `python apply_analysis.py data/daily_analysis.json`.

Щоденний аналіз за `BA_ANALYSIS_RULES.md` перевіряє вимоги, суперечності, мапінг, доречні винятки та приймання. У картці «Відкриті питання BA» показується, кому адресувати питання й яке рішення залежить від відповіді. «Чернетка опису задачі» містить англомовний CCON Task за `TASK_DESCRIPTION_RULES.md`; текст можна скопіювати для перевірки. Частково відомі вимоги відділяються від відкритих питань. Уже надані відповіді враховуються в наступному огляді.

Для підключення цих правил до **наявної локальної щоденної таски** онови файли застосунку й заміни її prompt текстом із `DAILY_AUTOMATION_PROMPT.md`. Збережи робочу папку й чинний розклад. Зміни репозиторію самі не оновлюють встановлені файли або prompt таски на комп'ютері. Окремий API ключ для аналізу не потрібен: його виконує агент Work/Codex. Реальний результат слід перевірити після першого запуску з доступом до Jira.

Підключення Jira: `python configure_jira.py`, введи email і токен у приховане поле. Токен зберігається локально у `.jira-credentials.json`, зашифрований Windows DPAPI для поточного користувача, і виключений із Git. На іншому Windows-акаунті налаштуй його повторно. Для середовищ без Windows використовуй `JIRA_EMAIL` і `JIRA_API_TOKEN`.

Rovo також підтримується: запусти `ROVO_PROMPT.txt`, збережи прикріплений файл як `inbox/CCON_BA_Snapshot.json`. Файл перевіряється кожні 3 секунди; dashboard оновлюється кожні 5 секунд і захищає незбережені редагування.

Правила листів уже задані в `EMAIL_RULES.md`: AER тема, Dear Team, без підпису, Logs attached for your reference. Відкриття через mailto передає лише текст — установи Aptos 11/чорний стандартним шрифтом Outlook. Логи прикріплюються вручну. Правила чернетки опису задані в `TASK_DESCRIPTION_RULES.md` на основі користувацького CCON BA Ticket Flow; вимоги не вигадуються.

«Автоматично» повертає автоматичну оцінку. Ручний статус завжди має пріоритет, зокрема DONE. Задачі, відсутні в новому snapshot, переходять до окремого списку; якщо повернуться — їхній стан відновиться. Імпорт не змінює Jira чи Confluence.

Snapshot — повний поточний набір задач, не часткове оновлення. Черга враховує ручний статус і пріоритет аналізу; початковий порядок допомагає при однаковій оцінці. Файл до 5 MB; ключі унікальні `CCON-number`, обов'язкові `summary` і `generatedAt` з часовим поясом. Інші поля — як у прикладі. Старіший snapshot відхиляється. Невалідний файл не змінює базу; повідомлення показується в dashboard.

## Де зберігаються дані

- `ba_state.db`: оцінки Rovo, ручні статуси, нотатки, відсутні задачі.
- `inbox/CCON_BA_Snapshot.json`: останній snapshot; замінюй щодня.
- `data/jira_context.json`: повні описи, коментарі та доступні залежності, локальний контекст аналізу.
- `data/daily_analysis.json`: аналіз агента з відбитками контексту. Зміна джерел позначає старий аналіз як застарілий.
- Папка логів із локального `log_config.json` (або `logs` біля застосунку): вихідні ZIP, XML постачальника, готові архіви, методи/помилки в facts.json і актуальний index.json. Архіви та конфіг виключені з репозиторію.
- «Експорт стану»: читабельна JSON копія для перегляду або контексту Rovo. Відновлення з JSON у прототипі не реалізоване.

Для резервної копії **зупини сервер і скопіюй ba_state.db**. Для перенесення поклади цю базу поруч із server.py на новому комп'ютері. Не запускай дві копії сервера з однією базою. Runtime дані і `.python-path` виключені з Git.

Сервер доступний лише на 127.0.0.1. Це локальний однокористувацький прототип. Чернетка листа відкривається через стандартний поштовий застосунок; перед відправкою додай адресата й перевір текст.

Rovo не читає локальну SQLite автоматично. За потреби передай йому експорт стану як контекст. Імпорт сам зберігає ручні рішення незалежно від нової оцінки.

## Перевірка

`python check_project.py` — усі перевірки backend, frontend і пакета. Для перевірок frontend потрібен Node.js 24+, для запуску застосунку достатньо Python.

Окремо backend: `python -m unittest discover -s tests -v`.

Структура модулів і межі даних: [ARCHITECTURE.md](ARCHITECTURE.md). Пакет з явного списку джерел: `python build_release.py --output CCON-BA-Desk.zip`. Файли для пакета перелічені лише в `release_manifest.json`; робочі дані туди не входять.

Перевіряє HTTP імпорт, ручні зміни, наступний snapshot, повторний імпорт, відсутність/повернення задач, перезапуск, невалідні та застарілі дані, захист від запитів із стороннього сайту.

Попередня версія репозиторію з PowerShell toolkit зберігається в історії, commit `fa1790057990124247d61d0d2b39790284508029`.

## Робота на вимкненому комп’ютері

Поточна локальна automation потребує увімкненого ПК та Work/Codex. Вона не виконується у хмарі. Для незалежної роботи потрібен дозволений організацією хмарний запуск (Rovo/Jira Automation або GitHub Actions/сервер) і спільне сховище. Локальний файл може отримати оновлення лише після ввімкнення ПК та синхронізації. Хмарний deployment у цьому репозиторії не налаштовано.


### Відкрити всі листи в Outlook

Кнопка «Відкрити всі листи (N)» бере всі поточні задачі зі статусом «Написати листа», незалежно від пошуку та фільтрів. Ручні статуси мають пріоритет. Спочатку відкривається список: чернетки без адресата, теми чи тексту пропускаються. Натисни «Відкрити чернетки», щоб передати кожен готовий лист стандартній поштовій програмі Windows в окреме вікно. Outlook має бути стандартною програмою для mailto. Тексти й адресати беруться з поточних полів, включно з незбереженими правками.

Ця кнопка не надсилає листи й не змінює статус задач. Прикріпи логи та перевір кожен лист у Outlook. Підтвердження показує кількість переданих команд, а не гарантію створення вікон: їхню появу перевір у Outlook. У разі часткової помилки можна повторити лише невдалі. Повторне відкриття всього списку може створити дублікати.

### Автоматична підготовка логів

Готові файли доступні безпосередньо в «Чернетці листа» → «Логи до листа»: «Завантажити ZIP» і «Відкрити папку». Кожна задача має власну папку, кожен cconFlowId — окремий архів. У загальному перегляді листів посилання на ZIP розміщені біля відповідної задачі. Якщо частина прикладів ще не опрацьована, показується їхня кількість; якщо в Jira немає cconFlowId, це позначається явно. Нові архіви з’являються автоматично, без скидання введеного тексту.

Щоденний агент виконує `LOG_WORKFLOW.md` для актуальних задач «Написати листа»: знаходить cconFlowId у посиланнях Kibana в описі/коментарях Jira, завантажує через прямий GET сервісу CCON у чинній сесії, потім запускає `supplier_logs.py`. Ручні очікування, завершення та інші ручні статуси мають пріоритет. Скрипт залишає лише XML потрібного постачальника, нумерує обміни за seq#, зберігає вміст файлів і попередні версії. Перевірені однакові XML повторно не пакуються.

Нові листи використовують фактичний метод постачальника з помилкового обміну, наприклад `doByLocatorPullPnr`. Ручні чернетки не переписуються. Для автоматичного завантаження потрібні працюючі Codex/ПК, мережа й чинна сесія CCON; після завершення сесії агент повідомить про необхідність увійти. Скрипт не зберігає паролі чи cookies. Прикріплення ZIP у новому Outlook залишається ручним.

Для роботи окремо: `python supplier_logs.py plan`, потім для отриманого ZIP — `python supplier_logs.py ingest --issue CCON-123 --flow-id UUID --source "шлях/до/ZIP"`. Коротку постійну папку можна задати в `log_config.json`: `{"logsDir":"C:/CCON-Logs"}`. У ZIP застосунку є лише код і приклад конфігурації, без робочих логів.

## Щоденний звіт змін та перевірки якості (v2.3)

Після успішного застосування `apply_analysis.py` формується файл `data/daily_review_report.json`.
Звіт доступний у меню **Дані → Щоденний звіт змін і якості**, а також за
`/api/daily-report` (JSON) та `/api/daily-report.md` (читабельний текст).
Якщо аналіз ще не виконано, JSON API повертає `available: false`.

Звіт порівнює **останній імпортований аналіз**, а не лише Jira timestamp:
нові, змінені, завершені за AI-сигналом, повторно відкриті та незмінені задачі;
додані й зняті відкриті питання та оновлення джерел. Зняте питання **не означає**,
що відповідь отримано: агент має перевірити її у джерелах. Ручне `DONE`
не еквівалентне автоматичному `signal=DONE` і не змінюється звітом.

Перевірки якості попереджають про WAIT без підтвердження, WRITE без `needsEmail=true`,
DONE з відкритими питаннями, дії без evidence та чернетки без QA.
Попередження **не блокують** імпорт інших задач. `queueScore` тепер
має бути скінченним числом у діапазоні 0–100.

Якщо запис звіту не вдався після успішного імпорту, команда поверне `reportError`:
це не означає, що імпорт не відбувся. GitHub Actions перевіряє PR на синтетичних
даних без токенів, Jira-кешу, SQLite або робочих логів.

**Активація:** потрібно встановити оновлені файли на Windows і оновити prompt
чинної локальної automation. GitHub не встановлює зміни на ПК автоматично.

## v2.4: Повний BA-брифінг і вимірювана якість

Після встановлення оновлених файлів і Work prompt кожна задача повинна
містити `analysis.briefing` за `BA_DEEP_REVIEW.md`.
У dashboard з'являється «Ситуація за 30 секунд»: поточна й цільова поведінка,
факти з посиланнями, хронологія, матриця IF/THEN, QA, scope, ризики,
рівень готовності і список прочитаних або недоступних джерел.

`READY_FOR_REVIEW` означає **чернетка для перевірки бізнес-аналітиком**.
Це не статус Jira й не гарантія достовірності. Попередні аналізи без
`briefing` не ламають імпорт, але звіт відобразить попередження `BRIEF_MISSING`.

Порівняння якості на 20–30 справжніх Jira-кейсах виконується локально:
`py evaluation.py prepare --count 30`, далі заморожуються baseline та candidate,
незалежний рев'юер оцінює результати, `py evaluation.py score` рахує метрики.
Усі документи й оцінки залишаються в Git-ігнорованій папці `data/evaluation/`.
Повний порядок дій: `docs/BA_EVALUATION_RUNBOOK.md`.

Green CI перевіряє код, а не правдивість AI-висновків на Jira.
Без доступного реального набору й людського review якість лишається непідтвердженою.
Жодна дія BA-помічника не змінює Jira/Confluence і не відправляє листи.

## v2.5: Sprint-first queue, change tracking, daily prompt calibration

Нова документація: [Повний флоу та діаграми](docs/BA_SYSTEM_FLOW.md),
[Вимоги й Acceptance Criteria](docs/BA_PRODUCT_REQUIREMENTS.md),
[План хмарного перенесення](docs/CLOUD_MIGRATION_PLAN.md),
[Дизайн-система](docs/BRAND_STYLE.md).

Налаштуй авторитетну Jira board для активного спринту. Для постійної
щоденної роботи створи біля server.py файл `.jira-board.json`
(виключений із Git) із вмістом `{"boardId":123}`; заміни номер на
реальний Jira board ID. Тимчасове перевизначення доступне через env:

```powershell
$env:CCON_JIRA_BOARD_ID = "123"  # замінити на реальний номер Jira board
py jira_sync.py
```

Ідентифікатор має відповідати CCON board у Jira. Задачі всередині
активного спринту потрапляють у найвищу групу навіть із нижчим score;
поза спринтом оцінка залишається 0–100. Якщо board не вказано, dashboard
явно пише, що пріоритет спринту не підтверджено. Якщо налаштована board
недоступна або її сторінки прочитані неповністю, sync відхиляється,
захищаючи попередній snapshot. Jira Software board/sprint APIs read-only.

Поточний JQL не виключає blocked-задачі за label, аби не приховувати
роботу поточного спринту. Done виключається з робочої черги, але
коли задача зникає з JQL, система додатково читає актуальний статус.
Лише `statusCategory=done` з підтвердженого Jira GET означає
`JIRA_DONE`; інакше це `LEFT_SCOPE` (не автоматичне завершення).

Після кожного успішного `apply_analysis.py` оновлюється
`data/prompt_calibration/current.md`, який аналізується наступного
робочого запуску. Цей адаптивний список формується з контрольованих
діагностичних попереджень. Основні промпти не переписуються самі,
щоб не допустити неконтрольованого дрейфу чи вигаданих правил.

**Хмарний статус:** це все ще локальний застосунок. Хмарна архітектура
під приватний SSO, постійний PostgreSQL та незалежну модельну задачу
документована, але не розгорнута. Не відкривай localhost-порт в інтернет
і не завантажуй реальні Jira-контексти в публічний GitHub.

## v2.6: особистий хмарний BA-пілот

**Область аналізу: тільки мої CCON Jira-задачі.** Локально це
`assignee = currentUser()`. У хмарі обов'язково потрібен
`CCON_JIRA_ASSIGNEE_ACCOUNT_ID`, інакше Jira sync зупиняється,
щоб випадково не аналізувати задачі технічного акаунта.

Пріоритетність спринту не залежить від AI-балів. Новий факторний
рахунок 0–100: businessImpact 0–25, urgency 0–25, dependencies 0–20,
baDecision 0–20, actionability 0–10. Новий аналіз зобов'язаний
показати розклад балів; арифметична невідповідність відхиляється.

Для контрольованої хмари додано `model_analysis.py`, `run_daily.py`,
`cloud_scheduler.py`, `cloud_security.py`, `Dockerfile`, `compose.yaml`,
`Caddyfile` та `nginx.conf.template`. Приватна HTTPS вебверсія
передбачає лише одного авторизованого користувача й OIDC/SSO.
Скрипт запускається після 08:00 Europe/Warsaw, навіть коли твій ПК вимкнений.
Режим моделі потребує затвердженого HTTPS хоста, ключа та явного
`CCON_ALLOW_CORPORATE_AI_UPLOAD=YES`; за замовчуванням він вимкнений.

**Інструкція та обмеження:**
[docs/CLOUD_PILOT_RUNBOOK.md](docs/CLOUD_PILOT_RUNBOOK.md).
Це реалізований контейнерний пілот, але не розгорнутий сервіс.
Для реального логіну і робочих даних потрібна корпоративна інфраструктура,
дозволи, SSO, DNS, Jira account ID, board ID та затверджений model API.
SQLite у Docker volume призначена лише для одного користувача;
PostgreSQL, секрети в Vault, HA та резервування залишаються
production-фазою. Прямий публічний доступ до Python-порту заборонений.
Нові PR перевіряють Python, JavaScript, ZIP release та конфігурацію Compose.

## v2.7: Evidence Engine без зміни стандартного інтерфейсу

Базова картка й розташування блоків залишаються такими, як у v2.6. Немає перемикача режимів «Швидко / Глибоко / Лист». Нові Evidence та Questions відкриваються за потреби у згорнутих секціях звичного екрана. Локальний Codex використовує `docs/EVIDENCE_WORKFLOW.md`: для аналізу повний ZIP (REST, errors і один supplier), для прикріплення до листа тільки XML відповідного supplier.

## v2.8: три практичні результати на кожну задачу

Звичний вигляд dashboard збережено.

- **Аналіз:** `value_mapping.py` порівнює реальні значення REST request → supplier request і supplier response → REST response. У JSON зберігаються тільки назви полів, порівняння й можливі розбіжності, без конфіденційних значень. Результати мають статус **CANDIDATE_ONLY** до перевірки BA.
- **Логи:** у локальному Codex запускай `supplier_logs.py plan --mode evidence`, незалежно від `needsEmail`; у чинному авторизованому браузері отримуй ZIP. `supplier_logs.py ingest` із повного ZIP створює supplier-only архів для Outlook та окремий доказовий звіт REST/errors/supplier. Інші supplier-папки у вихідний ZIP не включаються.
- **Готові результати:** `draft_output.py` заповнює редагований чернетковий лист для кожної задачі, не змінюючи `needsEmail`. Поки перевіреного supplier-only ZIP немає, текст листа не стверджує, що логи вже прикріплені. Англомовний опис за `TASK_DESCRIPTION_RULES.md` має бути максимально стислим без втрати умов.

Синтетичні CI-тести не замінюють перевірки на корпоративних логах. Доступ до реальної Kibana та CCON залишається в локальному авторизованому середовищі користувача.

## v2.9: порівняння до 30 прикладів помилки

`kibana_evidence.py` планує авторизовані локальні перегляди; новий
`error_series.py` після **реального завантаження ZIP у локальній сесії**
групує до 30 незалежних flow за error code, supplier method та місцем,
де помилку **побачено**. Дедуплікуються повторні ZIP одного flow.
Приклад: `python error_series.py --issue CCON-123 --error-code AF_REJECTED --max-cases 30`.
Результат: `data/investigations/CCON-123.json`. Звіт вказує coverage,
невизначеність і **гіпотези** щодо root cause, а не самовпевнений вердикт.
Доступність реальної Kibana з GitHub CI не перевіряється.

Консолідований функціональний план і критерії готовності:
[`docs/PRODUCT_BACKLOG.md`](docs/PRODUCT_BACKLOG.md).

## v2.10: браузерний handoff і статус ZIP

`python local_downloads.py prepare` формує локальний план точних URL і шляхів saveAs; **лише авторизований Codex/Work у браузері** здійснює завантаження. `python local_downloads.py process` обробляє реально збережені ZIP, запускає supplier-only ingest та показує готовність кожного flow. Сам Python не входить у Kibana/CCON і не керує браузером. У звичному блоці «Логи до листа» показано готово/частково/очікує/застаріло/помилка та причину.

Детальний процес: [Evidence Workflow](docs/EVIDENCE_WORKFLOW.md). Фактична перевірка браузера на твоєму комп'ютері ще потрібна.

## v2.11: механічна перевірка доказів, QA і тексту

`ba_quality_gate.py` зіставляє короткі excerpt у підтверджених фактах і правилах із реально завантаженими Jira description/comments, перевіряє наявність ID правил і покриття POSITIVE/NEGATIVE/EDGE у `briefing.verification`, а також структурність і технічну точність `standardDescription`. Результат зберігається як `analysis.qualityGate` і показується у звичній згорнутій секції картки задачі. Непідтверджений статус READY_FOR_REVIEW автоматично знижується до NEEDS_CONFIRMATION. **Поява цитати у джерелі не доводить правильність бізнес-інтерпретації**; це залишається відповідальністю BA. Вигляд dashboard, листування, ручні статуси та Jira read-only без змін.

## v2.12: кандидати відповідей і історія BA-рішень

У звичній картці задачі, всередині вже наявних згорнутих секцій, з'явилися дві функції:

- **Question Answer Candidates:** `question_candidates.py` шукає в коментарях поточної Jira-задачі **новіші за дату створення відкритого BA-питання** коментарі зі спільними технічними ідентифікаторами або конкретними тематичними словами. Схожість означає **кандидат на перевірку**, а не доведену відповідь. Коментар можна вручну підставити у відповідь разом із посиланням, але статус OPEN **не змінюється автоматично**.
- **Decision Register:** `ba_decisions.py` зберігає окремі запропоновані, підтверджені, оскаржені й замінені рішення з джерелом, впливом, причиною та незмінним журналом подій. Події з AI timeline потрапляють лише в PROPOSED, навіть якщо модель написала CONFIRMED. Підтвердження, dispute і supersede робить тільки аналітик.
- Ці дії не переписують Jira, існуючу чернетку опису, збережені листи чи ручні нотатки. Посилання на джерело не дорівнює семантичній перевірці відповіді. Реальні нові коментарі Jira та якість добору потребують UAT.

## v2.13: REST/supplier contract shape і достовірність часу

`flow_diagnostics.py` формує для кожного приватного ZIP два аналітичні зрізи: кандидати API mapping (native supplier method, direction, null/repeated fields, equality/difference) та хронологію **лише за явними ISO timestamps**. Немає timestamp = немає доведеного порядку; повторний метод не дорівнює доведеному retry. Результат додається до `flowDiagnostics` у evidence manifest, проходить у BA аналіз і показується в існуючому згорнутому блоці доказів. Вихідний supplier-only ZIP для листа не змінюється; приватні payload values не зберігаються.

## v2.14: Task History + персональний Action Plan

Без редизайну: дві згорнуті секції у стандартній картці задачі.

- **Історія задачі**: приватна SQLite таблиця `task_history` фіксує зміни Jira/AI-опису, next action, статусів, ручних нотаток і збережених email drafts під час імпорту й збереження. Історичні версії не перезаписуються, однакові стани не дублюються. Попередні записи доступні сторінками; це історія **з моменту оновлення застосунку**, без ретроактивного вигадування минулих версій.
- **Мій план дій**: по кожній моїй Jira-задачі вручну додавай дію, виконавця, хто блокує, дедлайн, дату наступного контролю та стан OPEN/WAITING/DONE. Записи живуть локально в `data/actions` і зберігаються між Jira sync. AI nextAction є лише незбереженою пропозицією. Ендпоїнт `GET /api/action-plan` формує спільний список за пріоритетом active sprint, прострочення та листування. **Не надсилає сповіщень автоматично.**
- Для діагностики: `GET /api/history/CCON-123?offset=0&limit=20`, `GET /api/actions/CCON-123`, `POST /api/actions/CCON-123`. Будь-який запис у план дій, на відміну від AI-пропозиції, потребує дії користувача.

Вхідні приватні дані залишаються в локальній базі/файлах, не публікуються в GitHub. Для live UAT потрібно оновити локальний Codex/Desk з main і перевірити збереження станів після перезапуску.

## v2.15: точковий BA-аналіз та копіювання результатів

Після повного актуального локального Jira sync запусти `python one_task_review.py --issue CCON-123`. Скрипт повторно викликає **лише approved model для вказаної своєї Jira-задачі**, інші перевірені аналізи копіюються без викликів. Якщо будь-яка інша задача має stale/відсутній аналіз, необхідний повний щоденний прохід, щоб не приховати розбіжності. Застосовується той самий корпоративний AI approval gate, жодних записів у Jira. Ручні статуси, нотатки та відредаговані email drafts не змінюються. У стандартному блоці листа додано «Скопіювати лист» для поточних змін користувача, без нових режимів.

## v2.16: Prompt A/B із людським підтвердженням

`prompt_experiments.py` забезпечує локальний цикл `stage → generate baseline/candidate → assess → approve → rollback` з незмінними cohort і prompt hash. Під час generate використовується тільки компанією дозволена модель, два набори output оцінює людина за поточним `evaluation.py`; базові prompt файли не змінюються. До схвалення і успішного оцінювання на 20–30 **реальних** задачах addendum не потрапляє в `model_analysis.approved_prompts`. При відкаті відновлюється попередній prompt hash. Чинна структура dashboard без змін. Докладні кроки: [BA Evaluation Runbook](docs/BA_EVALUATION_RUNBOOK.md).

## v2.17: покриття ZIP та попередня типізація помилок

`evidence_health.py` обчислює покриття окремих Jira flow повними REST+supplier доказами, позначає неповні/missing ZIP та попередньо групує error codes у категорії й повтори. Вміст обмежений локальними верифікованими manifests одного supplier; не експортує жодних приватних payload values. Результат показується у звичному згорнутому блоці доказів без нових режимів. **Heuristic category не дорівнює доведеній причині збою.**

## v2.18: швидкий пошук і схвалена версія BA-опису

Пошук у стандартній черзі тепер підтримує кілька незалежних слів, Jira key, AF/KL чи AFKL, метод постачальника, REST scope, назви точних полів IF/THEN і пов'язані задачі. Спринт і пріоритет листів залишаються незмінними.

У вже наявній згорнутій секції «Чернетка опису задачі» додано **«Схвалити опис»** і перегляд відмінностей від попереднього вручну схваленого тексту. Схвалений примірник зберігається лише локально, не редагується AI і не передається в Jira. Після змін джерела Jira повторне схвалення вимагає актуального аналізу. Листи, нотатки та статуси залишаються без змін.

## v2.19: retrospective audit of BA priority scores

The daily review records 0–100 score changes (and changes to the five underlying factors), even when the issue text is unchanged. A >=20-point shift with the same verified Jira fingerprint and sprint status is flagged for **manual review**, not asserted to be AI bias or a Jira error. Scores without factor explanations receive a non-blocking quality warning. Legacy scores still load. The current dashboard, sprint/email ordering, manual statuses, notes, and drafts are unchanged. No external writes or score auto-correction.

## v2.20: approved-model input minimization (QA-08)

Defence in depth before the optional company-approved AI request: recursively drop credential-named fields (including camelCase/HTTP headers), strip URL query/fragment and reject URL userinfo, redact identifiable emails/phone labels, common access token formats and embedded private-key blocks. Synthetic payload tests inspect exactly what is handed to the HTTP client. Technical field names like TypeCode remain unchanged. This is **not formal DLP or authorization for real corporate-data egress**. Company permission and endpoint allowlist remain mandatory; no Jira writes or outgoing email.

## v2.21: Jira attachment browser handoff and local structural inspection (EVD-13 partial)

`python jira_attachments.py prepare --issue CCON-123` creates `data/jira_attachment_handoff.json` with **explicit Jira attachment IDs** and local `downloads/jira/` save targets. The already-authorized local browser must download each listed file to `saveAs`; Python does **not** open Jira URLs or extract credentials. Then `python jira_attachments.py process --issue CCON-123` inspects already-downloaded JSON/XML/ZIP with strict size, XML DTD, archive path/encryption and decompression checks. Source bytes stay private; only local hash-bound shape metadata can reach an approved model, and only while the Jira fingerprint and downloaded file hash still match.

PDF contents are **not extracted** in this version (explicit `PDF_TEXT_NOT_EXTRACTED`). Confluence/wiki and any unsupported file are likewise **not read**, so no verified content claims may be made from them. Shape data is not evidence of business-correct field values or root cause; human Jira/CCON UAT still required. Neither Jira attachment contents nor customer logs belong in public GitHub.

## v2.22: grouped evidence reliability (EVD-14/15, QA-07)

**Local ZIP retention is opt-in and conservative.** `python evidence_retention.py --retention-days 30 --quota-mb 2048` displays a **DRY_RUN** of unreferenced immutable log versions only. It never deletes by default. Review its counts and hashed candidate IDs. To explicitly apply, run `python evidence_retention.py --retention-days 30 --quota-mb 2048 --apply --confirm DELETE_UNREFERENCED_LOG_VERSIONS`. All currently index-referenced supplier ZIPs, original ZIPs and facts remain pinned even if expired. A missing/invalid index, external log directory, unsafe path or symlink blocks cleanup. If protected versions alone exceed quota, it reports that it cannot satisfy quota. This does NOT implement encryption at rest, certificate-based ACL audits, secure file shredding or Windows host task scheduling. Never claim those features are present. Cleanup results remain in gitignored `data/evidence_retention_last.json`, and raw ZIPs remain local.

**Error recurrence** now includes, where available, the *window of explicitly timestamped flow payload events* for distinct locally downloaded flows. This is NOT proof the error occurred at those timestamps or that the production failure rate increased. No missing timestamps are imputed from filenames, ZIP mtime or downloadedAt.

**QA regression fixture matrix** exercises AF/KL and Finnair, REST/errors, separate supplier-only XML archives, multi-error flows, candidate retries, nested ZIP isolation, malformed/XML entity payloads, and timezone-aware event chronology. Fixtures are synthetic; real corporate Kibana and supplier UAT remain pending.

## v2.23: grouped BA output quality (BA-01, BA-02, OUT-01, QA-04)

The existing collapsed Quality Gate now checks additional failure modes in machine-generated outputs: omitted exact confirmed technical field names and enum/code values in IF/THEN, missing AND/OR operator in compound rules, generic QA checks, open questions or rules despite a `READY_FOR_REVIEW` claim, and unverified claims that supplier logs are attached. With a verified supplier method, conflicting `during doXxx` method assertions are flagged rather than silently rewritten. These checks do **not** claim semantic truth or approve Jira changes; ambiguous drafts remain under human review. The approved model prompts are **not** modified by this PR (frozen 20–30 real-case A/B and human approval still apply). Existing manual notes, statuses, saved email drafts and dashboard layout remain intact. No email is automatically sent.

## v2.24: local source verification (grouped EVD-13/BA-09/OUT-04)

The desk can now cross-check an analyst-provided source quote against **exact local bytes**, not just an unread attachment link. The authorized user obtains JSON/XML/ZIP/PDF Jira attachments and linked Confluence page HTML using the two local handoffs in `docs/EVIDENCE_WORKFLOW.md`. Content is parsed **only locally** within strict quotas, format and integrity checks. The optional `pypdf` parser is not automatically installed; scans and unsupported PDFs remain unread. Missing or tampered documents cannot be cited as locally read. The existing Quality Gate records source coverage and candidate differences in field assignments without elevating them to proven discrepancies. Neither raw document text nor private HTML is sent in model requests or committed to the public repository. Synthetic regression tests do not substitute for a live company-authorized browser and analyst review.

## v2.25: focused BA descriptions and measurable offline quality

For generated descriptions only, the desk drops exact immediately duplicated implementation lines; it never auto-summarizes or drops a technical condition or QA scenario. The original dashboard shows structural density counts inside the existing closed Quality Gate details. `python evaluation.py score`, after freezing **both** baseline/candidate predictions for a local **20–30 real Jira task cohort**, adds deterministic, source-safe A/B warning metrics. All local cases and manual human scores remain private under `data/evaluation/`. Real-case gold-set acceptance is still a separate human step; synthetic CI does not validate business truth.

## v2.26: UX/productivity аудит і швидкий локальний dashboard

Для великих особистих беклогів додано легкий `GET /api/tasks/revision`: інтерфейс не перечитує кожні 5 секунд усі Jira-задачі, якщо стан не змінився; не навантажує приховану вкладку. Пошук не індексує технічний текст, доки немає реального запиту. SQLite збільшує revision в тій самій транзакції, де імпортується snapshot або зберігається ручна правка. Старі status/note/email drafts і вигляд картки не змінюються.

Проведено **product-manager аудит усіх ключових BA-шляхів** і додано 73 окремі backlog items із acceptance criteria та планом пакетних PR. Це програмний та евристичний огляд, **не** тест із реальними користувачами: `docs/PRODUCTIVITY_UX_AUDIT.md`, `docs/UX_TEST_COVERAGE_MATRIX.md` і `docs/LOCAL_PERFORMANCE_RELIABILITY.md`.

Для замірів без корпоративних даних: `python performance_smoke.py --sizes 100 500 1000 --iterations 25`. Він створює тимчасові **синтетичні** SQLite snapshots і показує p50/p95 server-side local `Desk.view()` проти `Desk.revision()`. Browser/UI швидкодію, роботу на Windows і BA time-to-handoff потрібно виміряти вручну за runbook. Відкат на попередній release можливий після приватної резервної копії `ba_state.db`; таблиця `state_revision` лише додається, існуючі ручні правки не видаляються.

## v2.27: безпечні ручні правки у двох вкладках

При збереженні статусу, нотатки чи редагованого листа застосунок перевіряє версію **саме цієї** задачі. Якщо інша вкладка змінила її першою, сервер повертає `409 Conflict`: твої незбережені правки **не перезаписуються**. На сторінці видно попередження та поточну збережену версію (статус, нотатка, лист); після порівняння можна свідомо перезаписати її своєю версією або прийняти збережену. Ніякі Jira-дані чи листи назовні не змінюються.

Перехід із попередніх версій не стирає `ba_state.db`: нове поле `manual_revision` у SQLite додається автоматично. Browser recovery фіксує початкову версію; старі чернетки без неї не зберігаються сліпо. **Важливо:** власні зовнішні скрипти, які викликають POST без `expectedManualRevision`, поки збережені для сумісності й не отримують цю гарантію. Інтерактивне тестування двох вкладок і аварійного відновлення на Windows залишається відкритим.

## v2.28: швидкий маршрут для BA без нового режиму інтерфейсу

У звичній картці Jira-задачі найближча дія з'являється одразу після назви та статусів. Її можна скопіювати. Поруч доступна кнопка **«Скопіювати Jira-чернетку»**, але тільки коли актуальний аналіз успішно пройшов **структурну** перевірку Quality Gate. Це **не** доводить правильності вимог: перевір IF/THEN, джерела та QA перед ручною передачею в Jira. Детальна чернетка й інші докази залишаються в уже наявних секціях.

Згорнутий блок **«Чому задача в цій позиції черги»** пояснює поточне сортування: підтверджений спринт → справжня потреба у листі → сигнал → 0–100 → блокування. Сортування не змінювалося. Повторне оновлення того самого завдання зберігає позицію прокрутки й відкриті підрозділи.

**«Виконано → Далі»** тепер запитує підтвердження, що фактична робота завершена вручну. Те саме застосовується до вибору DONE у статусі. Відкрити лист, скопіювати чернетку чи перейти в Jira ≠ надіслати/виконати дію. Підтвердження змінює лише локальний стан; Jira та пошта автоматично не редагуються.

Офлайн-умовні тести `tests/fast-handoff.test.mjs` не замінюють UX та фактологічний UAT: реальні 5 сценаріїв і порівняння часу до передачі, фокуса й доступності залишаються відкритими.

## v2.29: трудомісткість XS–XL і обережні підказки коротких задач

У звичному блоці «Мій робочий стан» можна вручну встановити **XS (до 2 хв), S (2–5), M (5–20), L (20–60), XL (понад 60 хв)** або `UNKNOWN`, зберігши разом із нотатками. Значення зберігається лише локально в SQLite, не публікується в Jira, не перезаписує листи й захищене від конфліктів між вкладками. Старі бази оновлюються адитивно.

Коли ручного значення немає, показується **детермінована попередня оцінка** за структурою задачі: сигнал, Quality Gate, кількість правил і відкритих питань, готовність листа. Вона має **низьку впевненість**, не є реальним заміром часу і не стверджує фактологічної правильності.

Невеликі потенційні quick wins у черзі отримують стриману позначку `S?`; активні задачі з помилками, відсутніми умовами, WAIT, DONE або застарілим контекстом її не отримують. **Порядок сортованої черги не змінюється**: жодна XS не обходить sprint/WRITE/action rank/score/blocking.

Контракти, приклади й гейт людських замірів: `docs/EFFORT_PRIORITIZATION.md`. Синтетичні тести перевіряють інваріанти та міграцію, але не доводять реального часу BA.

## v2.30: клавіатурна навігація та безпечне повернення до задачі

У звичному списку з'явилась коротка розгортувана підказка клавіш: `/` відкриває пошук, `Alt+↓/↑` переходить по **видимому фільтрованому** списку без зміни пріоритету, `Alt+C` копіює поточну перевірену наступну дію, `Ctrl+Enter` (або `Cmd+Enter`) зберігає ручні правки з існуючим захистом від конфліктів. Навігація не перехоплює введення тексту та не працює у вікні пакетних листів.

Повернення до відкритої задачі в тій самій вкладці зберігає вибір, позицію списку/деталі, відкриті секції й координати курсора без автоматичного перемикання фокуса зі списку на textarea. У `sessionStorage` зберігаються тільки технічні ідентифікатори/хеші, не текст Jira, нотаток чи листів. Після Save, під час локального збою або конфлікту видно окремо **незбережено / зберігаю / помилка / конфлікт**, а не хибну зелену готовність. Модальний список листів безпечно повертає клавіатурний фокус після закриття.

Детальна поведінка й тести: `docs/FOCUS_KEYBOARD_UX.md`. Реальна Chrome/Edge/Windows, IME, screen reader та time-to-resume перевірка ще потрібна.

## v2.31: швидка черга на 100, 500 і 1000 задач

Пошук тепер використовує **кешований індекс поточного snapshot** і затримку 130 мс під час набору, не перечитуючи довгі технічні описи для кожної літери. При нових даних або зміні ручного статусу кеш автоматично скидається. Натискання на задачу більше не перемальовує весь список; нотатки під час набору оновлюють тільки індикатор незбереженості.

Локальний сервер кешує повну JSON-відповідь `/api/tasks` до наступної транзакційної ревізії SQLite, перевіряючи також зміни з іншого процесу. Безпека, приватні статуси/чернетки, правила активного спринту й листування не змінювалися. Звичний інтерфейс та робота без cloud залишаються.

Синтетичні перевірки: `python performance_smoke.py --sizes 100 500 1000 --iterations 25`, `node queue_benchmark.mjs --sizes 100 500 1000 --iterations 25`. Вони показують p50/p95 SQLite/Node, **не реальну швидкість інтерфейсу в Chrome або Windows**. Повні браузерні заміри і 8-годинний тест залишаються відкритими. Методика й критерії: `docs/LARGE_QUEUE_PERFORMANCE.md`.

## v2.32: приватний backup і відновлення після збою

Локальна база `ba_state.db` тепер резервується через SQLite online backup API **перед міграцією при старті** (за потреби, якщо немає свіжої 24-годинної копії), а також приблизно щодня. Вміст копії перевіряється, хешується SHA-256 і зберігається у приватній `backups/` (до 7 останніх копій, `gitignore`). У звичному меню «Дані» відображається дата останньої копії й стан автоматичного імпорту; жодного нового таба чи автозавантаження назовні.

**Ручні команди з каталогу програми:**

```powershell
py -3 local_backup.py status
py -3 local_backup.py backup
py -3 local_backup.py verify --name backup-YYYYMMDDTHHMMSSZ-XXXXXXXXXXXX.sqlite3
```

**Відновлення лише після зупинки сервера й закриття вкладок** через явну CLI-команду, яка спершу створює додаткову rescue-копію:

```powershell
py -3 local_backup.py restore --name backup-YYYYMMDDTHHMMSSZ-XXXXXXXXXXXX.sqlite3 --confirm "RESTORE LOCAL BA DATA"
```

Уважно прочитай `docs/PRIVATE_BACKUP_RESTORE.md`: копія містить приватні тексти в SQLite, **не зашифрована** й має зберігатися тільки на захищеному Windows диску (BitLocker/ACL). Вона **не** охоплює незбережені браузерні форми, локальні файли `data/` та supplier ZIP. При аварійному restore можливі втрати змін після часу backup. Перевірки Windows crash/restart і 2 browser tabs залишаються відкритими; проходження CI їх не замінює.

## v2.33: окремі незбережені чернетки для кожної вкладки та доступність

Раніше відкриті вкладки використовували **один** `localStorage` ключ, тому незбережені нотатки й листи могли перезаписуватися. Тепер кожна вкладка має власний довготривалий запис, який зберігається при Reload. Коли браузер створює копію вкладки, вбудований `BroadcastChannel` намагається автоматично відокремити її ID. SQLite CAS залишається обов'язковою фінальною перевіркою.

У звичному меню **Дані** можна вручну **відновити чернетки з іншої вкладки** або **очистити набори старші за 30 днів** після явного підтвердження. Відновлення не перезаписує незбережений текст поточної задачі; інша вкладка не втрачає свою копію. Якщо браузерне сховище заблоковане, показується попередження: **збережи правки в SQLite перед закриттям**. Нових режимів, автоматичних Jira updates або надсилання email немає.

Черга має тихе повідомлення для screen reader про вибрану задачу. Для 320px / високого контрасту й `reduced motion` додані стилі без зміни звичної широкої сторінки. Реальний NVDA/Chrome/Edge/400% zoom та 8-годинний UAT ще відкриті.

**Приватність:** локальні незбережені чернетки залишаються **незашифрованими** в профілі браузера й **не входять** до SQLite backup із PR #32. Працюй у захищеному персональному профілі на диску з шифруванням. Деталі й тест-план: `docs/BROWSER_RECOVERY_ACCESSIBILITY.md`.

## v2.34: справжні браузерні E2E та аудит надлишкового UI

CI тепер має окрему задачу **Chromium browser-e2e**. Вона запускає локальний HTTP server із вигаданими задачами та через реальний браузер перевіряє клавіші, фокус, дві вкладки й конфлікт CAS, незбережені чернетки, недоступний /api/tasks/revision, відновлення читання без повторного POST, модальне вікно та коротку сесію з 90 виборами задач. Браузерні результати містять лише синтетичні тести, не корпоративний Jira/ZIP/PNR.

Як повторити окремо в тестовому середовищі:

```bash
python -m pip install playwright==1.56.0
python -m playwright install chromium
python browser_e2e.py
```

Playwright **не потрібен для звичайного запуску** BA Desk на Windows. Реальний Windows/Edge/NVDA та восьмигодинний прогін залишаються окремою ручною перевіркою. Політика reconnect робить тільки контрольовані повторні GET (до 60 сек. паузи), **ніколи не повторює Save, DONE або email** без людини.

**Заплановане спрощення інтерфейсу:** `docs/UX_REDUNDANCY_SIMPLIFICATION_AUDIT.md` містить попередній аналіз 16 потенційно зайвих або повторюваних елементів із доказами у коді, ризиком їх приховування та пакетами #35–38. Нічого не видалено: спочатку browser/human BA UAT, потім обережне об'єднання або згортання в існуючій сторінці.

## v2.35: спокійніша черга й зрозумілі статуси

Без нової сторінки чи режимів. У лівій черзі видно лише `N у списку · спринт M · листи L`; усі додаткові метрики доступні в згорнутих `Деталі черги`. У картці Jira-статус, мій стан і належність до спринту мають **різні підписи**, а активні блокери, листи та очікування лишаються помітними. Дубльований порожній брифінг прибрано, але попередження про відсутній/застарілий аналіз, QA gate, опис Jira, докази та історія не зникли. Висновок про економію часу потребує реальних 5 BA сценаріїв, тести лише захищають семантику.

## v2.36: дії без дублювання та ризику помилкової передачі

У стандартній картці лише один активний Copy структурно перевіреної Jira-чернетки. Якщо QA ще не пройдено, текст доступний у деталях із попередженням «для доопрацювання», а локальне схвалення BA залишається окремою кнопкою. «Скопіювати лист», «Відкрити в пошті (без надсилання)» й «Пакет листів» мають різний зміст; жодна дія не відправляє лист автоматично. Повторний великий блок оцінки XS–XL згорнуто разом із причиною пріоритету. Тести не замінюють перевірки джерел людиною.

## v2.37: функції доступні, але менше візуального шуму

За замовчуванням ліворуч пошук і головний фільтр задач. Сигнал і спринт в `Додаткові фільтри` з постійним індикатором кількості активних умов. У «Дані» існуючі команди згруповані за призначенням. У картці блок доказів згорнуто під заголовком із кількістю джерел, історію та старі аналізи згруповано під `Історія й аудит`. Якість аналізу (Quality Gate), відкриті питання й робоча чернетка залишаються доступними. Реальний аналіз NDC/REST/ZIP та Windows accessibility UAT не замінено synthetic CI.

## v2.38: безпечне CSS-прибирання та план фінального завершення

Видалено лише неактивні стилі попередньої статусної панелі, без зміни знайомого дизайну. Chromium E2E додатково зберігає **синтетичні** скриншоти 320/768/1440 і перевіряє горизонтальне переповнення; Windows/Edge/NVDA й реальні 400% zoom ще потребують UAT. `docs/BACKLOG_CLOSEOUT_PLAN.md` містить повний облік **129** основних пунктів і план оптимальних **10 додаткових тематичних PR #39–48** для стабільної локальної версії. Cloud P3 залишається відкладеним; фактичну бізнес-правильність можна підтвердити лише на 20–30 приватних BA gold-cases.

## v2.39: єдиний перевірюваний backlog і критерії готовності

Не всі позначені `IMPLEMENTED (code)` пункти мають людське підтвердження. `docs/BACKLOG_ACCEPTANCE_LEDGER.json` тепер містить **129 рядків** із незмінним початковим статусом, окремим `human_acceptance=NOT_RECORDED`, маршрутом до тематичного PR, ризиком дублювання і конкретним посиланням на код/тест (де його перевірено). Автоматичний CI перевіряє синхронізацію: `python backlog_audit.py --check`. Після зміни `docs/PRODUCT_BACKLOG.md` повторно згенеруй реєстр командою `python backlog_audit.py` і переглянь diff.

`docs/BACKLOG_RECONCILIATION.md` описує **9 перетинів вимог** для можливого об’єднання приймання, без видалення функціоналу. `docs/BA_GOLD_CASE_ACCEPTANCE.md` задає 26 рекомендованих приватних кейсів для BA, QA-02/03/10/13 та межу synthetic CI. Розрахункова робота після #39: **9 тематичних PR #40–48 плюс людський UAT**. Cloud/SSO P3 поки не входить до локальної версії.

## v2.40: безпечне зіставлення REST ↔ supplier та актуальність джерел

ZIP review більше не прирівнює єдині RQ/RS із **різними explicit correlation IDs**, а також не зіставляє повторні REST операції з одним supplier exchange. Результат показує кандидатні пари й кількість exchange без пари за напрямом, але не публікує values/IDs. Всі mapping залишаються **CANDIDATE_ONLY**, не фактом бізнес-правила.

Коли локально підтверджена Confluence-сторінка або Jira attachment змінила hash/verification, попередній кешований BA-аналіз переглядається, навіть коли Jira fingerprint той самий. Правила й приватні UAT-приклади: `docs/EVIDENCE_PROVENANCE_CONTRACT.md`. Live Jira/Kibana/CCON evidence та незалежний семантичний BA review досі потрібні; git CI використовує лише synthetic дані.

## v2.41: листи лише з перевіреним твердженням про вкладення

Завдяки повному статусу supplier ZIP у задачі, одна підготовлена архівація з кількох очікуваних flow більше не означає `READY`. Підготовлений email не буде автоматично говорити «Logs are attached», якщо хоча б один потрібний файл відсутній, застарів або потребує review. За замовчуванням генератор листа не робить такого твердження; лише explicit `attachment_ready=True`. Людина все ще вручну перевіряє адресата, метод, вкладення у пошті та Jira-опис. `docs/HANDOFF_GATE_CONTRACT.md` містить точний протокол.

## v2.42: Скасувати останнє локальне «Виконано»

Після успішного ручного `DONE` у верхньому рядку з’являється одна кнопка `Скасувати «Виконано»`. Вона повертає тільки попередній локальний статус через захищений ревізією SQLite запит і не змінює Jira та не надсилає пошту. Якщо інша вкладка вже змінила задачу, Undo зупиниться з попередженням. Кнопка не переживає перезапуск браузера та не є автоматичним відкатом усіх змін.

## v2.43: адреса постачальника лише за явним вибором, пріоритет без обхідних шляхів

Назва Jira-задачі більше не заповнює автоматично поле «Кому» у чернетці листа. Якщо відомий шаблон адреси, поруч доступна кнопка `Вставити адресу зі шаблону` з обов'язковим видимим застереженням про ручну перевірку адресата. Видалена користувачем адреса залишається порожньою після Save/Reload. Це **не** перевірка актуальності supplier inbox. Після внесення будь-якої адреси лист усе ще відкриває людина.

Додано окремі жорсткі регресії: verified active sprint завжди вище backlog; WRITE вище READY у своєму lane незалежно від бала; DONE нижче відкритих; unverified sprint не стає verified; effort/quick suggestions не перезаписують ranking. Real time-to-action BA UAT ще відкритий.

## v2.44: контрольні приклади для RCA без вигаданого успіху

Для розслідування конкретної помилки додаються окремі bounded `contrastCandidateFlowIds`: це інші локальні flows того самого issue/supplier, де цей код **не спостерігався**, а не гарантовані успішні замовлення. Вони не збільшують affected-case статистику, не доводять root cause і потребують перевірки через повні REST/supplier RQ/RS та confirmed contract у приватному середовищі. Докази й приклади: `docs/RCA_CONTRAST_VALIDATION.md`.

## v2.45: валідність часу резервних копій SQLite

Створені локально SQLite backup тепер підтверджують ідентичність UTC-моменту в імені файлу та JSON-маніфесті. Неправильна, неоднозначна або підроблена дата не робить копію «свіжою», а корекція системного годинника назад не повинна блокувати нове резервування. Повний Windows power-loss/BitLocker/ACL UAT окремо в `docs/BACKUP_CLOCK_INTEGRITY.md`. Ніякого автоматичного restore не додається.

## v2.46: Chromium-навантаження на чергу 100/500/1000 задач

Синтетичний browser E2E перевіряє cold reload списку на 100, 500 і 1000 задач та вимірює затримку пошуку в реальному Chromium DOM. Результати зберігаються лише як агрегати у тимчасовому CI artifact без Jira/PNR. Заміри **не є Windows SLA**, не гарантують швидкість на реальних довгих Jira описах, Chrome/Edge чи 8-годинній сесії. Додатково виправлено пошук за самими розділовими знаками: порожній folded-токен більше не шукає «всі задачі».

## v2.47: доступність наявного екрана, без нових режимів

Групові заголовки Sprint/Backlog/Done у черзі мають семантику заголовків для допоміжних технологій; індикатор `S?` більше не залежить лише від mouse hover і вказує на непідтверджену оцінку. Додано синтетичні Chromium-перевірки видимості основних ручних дій, фокусу, 320px, forced-colors і reduced-motion. **Windows/NVDA та нативний 200/400% zoom не перевірені цим CI.** Деталі: `docs/A11Y_FINAL_SCOPE_REVIEW.md`.

## v2.48: Engineering closeout, release gate ще не пройдений

Пакети реалізації #39–48 охоплюють рекомендований локальний цикл інженерних покращень. **Це не означає завершення всіх 129 вимог і не є дозволом на production deployment.** Реальний Jira/Kibana/CCON source-review, 20–30 приватних BA gold cases, Windows crash/restore, Edge/NVDA/400% zoom і 8h soak залишаються неперевіреними зовнішніми критеріями.

`python release_readiness.py --check` перевіряє узгодженість обліку й не стверджує release readiness; `python release_readiness.py --require-ready` має завершитися помилкою до незалежної приватної UAT-атестації. Сам факт злиття GitHub PR не оновлює Windows Task Scheduler або локальну інсталяцію. Інструкція з контрольованого випуску: `docs/LOCAL_RELEASE_GATE_v2_48.md`.
