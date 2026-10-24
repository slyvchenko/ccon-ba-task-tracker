# Структура CCON BA Desk

Застосунок працює на Python standard library, SQLite і браузерних ES modules. Для запуску не потрібні npm, збірка frontend чи додаткові Python пакети.

| Частина | Відповідальність |
| --- | --- |
| `server.py` | Локальний HTTP, дозволені статичні файли, запуск і спостереження за snapshot |
| `desk_store.py` | SQLite, імпорт snapshot, ручні статуси/нотатки/чернетки, доступ до контексту |
| `schema.py` | Спільна перевірка типів і обмежень даних |
| `app_config.py` | Шляхи, версія, статуси, ліміти й UTC timestamps |
| `storage.py`, `pipeline_lock.py` | Атомарний JSON, перевірка меж каталогів і блокування паралельних записів |
| `mail_service.py`, `email_rules.py` | Перевірений mailto і правила нових згенерованих листів |
| `jira_sync.py`, `configure_jira.py` | Читання Jira та локальне налаштування доступу |
| `apply_analysis.py` | Повнота й актуальність аналізу перед застосуванням |
| `supplier_logs.py` | План завантажень, очищення XML, методи/помилки, незмінні версії ZIP |
| `log_attachments.py` | Архіви окремої задачі, перевірка завантаження, відкриття папки |
| `dashboard.html` | Розмітка сторінки |
| `assets/dashboard.css` | Стилі з чинним порядком каскаду; старі картки та статусні чіпи видалені |
| `assets/dashboard.mjs` | Форми, відображення задач, збереження й поштові дії |
| `assets/task-rules.mjs` | Правила статусів, сортування, фільтрації та адресатів без залежності від DOM |
| `assets/logs.mjs` | Оновлення архівів без заміни редагованого листа |
| `release_manifest.json`, `build_release.py` | Один явний список файлів для ZIP, перевірка цілісності пакета |
| `tests/`, `check_project.py` | Перевірки backend, frontend і автономності ZIP |

## Межі даних

Ручний стан живе в `ba_state.db`, повний контекст — у `data/`, snapshot — у `inbox/`. Оригінальні й очищені логи залишаються в каталозі `log_config.json`. Ці дані та credentials не є кодом і не входять у ZIP або репозиторій.

Jira sync, аналіз і підготовка логів ділять одне блокування. Записи JSON виконуються через тимчасовий файл та атомарну заміну. HTTP не роздає довільні файли: лише явний список frontend-файлів і перевірені архіви за ключем задачі та flow.

Ручний статус має пріоритет. Застарілий аналіз не визначає дію; збережена ручна чернетка не переписується новим аналізом. Браузер зберігає незбережені форми під тим самим ключем localStorage, що й до поділу frontend на модулі.

## Перевірка й пакет

`python check_project.py` запускає Python тести, перевірку синтаксису модулів і Node тести правил черги та асинхронних відповідей. Node потрібен лише для перевірок розробника.

`python build_release.py --output CCON-BA-Desk.zip` створює пакет з файлів `release_manifest.json`. Після додавання runtime-модуля чи asset додай його до manifest; перевірки пакета виявляють відсутні залежності й статичні файли.

Команди користувача й щоденного агента залишилися тими самими: `server.py`, `jira_sync.py`, `supplier_logs.py`, `apply_analysis.py`.

## v2.3: детермінований звіт якості

`review_report.py` порівнює попередній аналіз зі свіжим результатом;
ігнорує пробіли, порядок питань і косметичні зміни оцінок.
Фіксує нові/оновлені/завершені/повторно відкриті задачі та неблокувальні
діагностичні попередження. Звіт записується атомарно у JSON
**тільки після успішного імпорту** snapshot.

HTTP-маршрути `/api/daily-report` і `/api/daily-report.md` показують
структурований і читабельний вигляд локально. Markdown будується з JSON
на запит, тож дві копії звіту не розходяться. Ці маршрути не можуть
змінювати Jira, листи чи ручні рішення. CI працює з синтетичними даними.

## v2.4: source-grounded BA dossier and independent evaluation

`ba_briefing.py` adds optional validated `analysis.briefing` to legacy schema.
Evidence, decision timeline, conditional rules, QA, source-read audit and
readiness are displayed by `assets/dashboard.mjs` without any write API.
`review_report.py` issues non-blocking warnings for incomplete dossiers.

`evaluation.py` is a separate **local-only** workflow: it freezes 20–30 real
Jira contexts in `data/evaluation/`, accepts paired frozen predictions tied
to those fingerprints, and computes quality metrics exclusively from
human-completed rubric scores. No user content is uploaded to CI/GitHub.
Evaluation is not performed automatically on an inaccessible Jira instance.
