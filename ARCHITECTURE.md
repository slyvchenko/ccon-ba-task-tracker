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

## v2.5: sprint, change provenance, prompt calibration and cloud plan

`sprint_priority.py` читає статус active з вказаної Jira Software
board і перевіряє всі сторінки membership; повертає VERIFIED
або NOT_CONFIGURED, але не здогадується про спринт з тексту задачі.
Нові `activeSprint` поля впливають на чисті функції сортування
в `assets/task-rules.mjs`. Робочі завдання активного спринту завжди
вище відкритого беклогу незалежно від score 0–100.

`jira_sync.py` додатково перевіряє задачі, що залишили JQL,
за актуальним Jira statusCategory. `review_report.py` показує
`JIRA_DONE` лише після підтвердження, інакше `LEFT_SCOPE`.

`prompt_calibration.py` оновлює локальний датований checklist
з фіксованих попереджень коду після успішного `apply_analysis.py`.
Інструкції з Jira не використовуються як правила. Ядро промптів
лишається під code review та реальним human A/B evaluation.

Повні потоки, каталог модулів, послідовність task lifecycle і
цільова приватна хмара: `docs/BA_SYSTEM_FLOW.md`.
Cloud design gate: `docs/CLOUD_MIGRATION_PLAN.md`.

## v2.6: runnable single-analyst cloud pilot

Private HTTPS SSO edge: `Caddyfile` -> `nginx.conf.template` ->
`oauth2-proxy` OIDC -> `cloud_security.py` exact allowed user + proxy
shared secret -> `server.py` cloud mode. The Python backend is not
published as a Docker host port. Manual state is local to an
encrypted-host-volume-dependent SQLite pilot, **not** managed Postgres.

`run_daily.py` requires cloud mode, a personal Jira account ID, and
approved HTTPS model egress before fetching Jira data. `jira_sync.py`
never relies on the technical API principal's `currentUser()` in cloud
mode. `model_analysis.py` caches unchanged fingerprint+notes+prompt
analyses and atomically publishes a complete output set;
`apply_analysis.py` validates and commits the result locally.
`cloud_scheduler.py` tracks successful Warsaw calendar dates.
External Jira/Confluence write operations and auto-send email
remain absent. See `docs/CLOUD_PILOT_RUNBOOK.md`.

## v2.26: швидка локальна робота з великою чергою

- `desk_store.py`: `state_revision` з одним монотонним інкрементом **у транзакції** snapshot import / manual save. Невдала або повторна операція не змінює revision. `Desk.revision()` читає тільки одне число, а не декодує всі JSON-снапшоти.
- `server.py`: новий приватний GET `/api/tasks/revision` із тим самим auth/host/CSP контрактом, що й `/api/tasks`. Формат: `{"revision": integer, "error": string}`. GET `/api/tasks` лишився backward compatible, має додаткове поле `revision`.
- `assets/dashboard.mjs`, `assets/revision-policy.mjs`: після першого повного завантаження кожні 5 с у видимій вкладці перевіряється маленький токен. Повний список знову завантажується **тільки при зміні revision/error** (або невалідному токені). Background tab не опитує сервер; focus запускає перевірку. Логи оновлюються раз на ~15 с, звіт і health раз на ~30 с.
- `assets/task-rules.mjs`: спочатку cheap predicates active/sprint/signal, а без пошукового запиту не формується довгий текст із technical rules. Hard priority sprint/WRITE/score збережений.
- `performance_smoke.py`: синтетичний SQLite benchmark для 100/500/1000 задач, **не** браузерний результат, не корпоративний контент. У `tests/` нові Python HTTP/restart/concurrency і Node пошук/revision тести.
- Вся UX-програма: `docs/PRODUCTIVITY_UX_AUDIT.md`, `docs/LOCAL_PERFORMANCE_RELIABILITY.md`, `docs/UX_TEST_COVERAGE_MATRIX.md` і canonical backlog у `docs/PRODUCT_BACKLOG.md`. Це **не новий режим UI** і не автоматична відправка Jira/email.

### Межа перевірки

Монотонна ревізія є сигналом синхронізації **лише змін, зроблених цим застосунком**; вона не замінює compare-and-swap для двох вкладок. SQLite зберігає ручний статус і нотатки, але CAS та crash-backup залишаються окремими P0. У CI немає підстав стверджувати виміряну p95 latency на Windows або семантичну якість BA.

## v2.28: quick-action BA policy within the original task card

`assets/fast-handoff.mjs` holds a pure, independently testable presentation policy: current next action, conditional shortcut to a structurally checked Jira draft, ranked-lane explanation and explicit confirmation prompt for **manual** work completion. It imports the authoritative `assets/task-rules.mjs` so no second ranking algorithm or new task modes are introduced.

`assets/dashboard.mjs` puts the current action at the top of the **same existing detail card**, no extra tabs or separate Quick/Deep mode. Copying a text changes only the clipboard and never confirms an external Jira/email operation. The shortcut stays disabled for missing, stale, BLOCKED or merely NEEDS_REVIEW reports. The original detailed review remains accessible. Both Done→Next and manual Done status require user confirmation. Existing per-task SQLite CAS continues to protect edits.

On same-task refresh, selection, sidebar/main scroll and open details are retained where available; user-entered drafts are guarded by the existing form and conflict-policy mechanism. This is a UI convenience, not a semantic or live supplier validation.

## v2.29: advisory effort estimates as separate local task state

`desk_store.py` migrates `tasks.manual_effort` to `UNKNOWN` on old DBs. The optional `manualEffort` key is checked against exactly XS/S/M/L/XL/UNKNOWN; a save updates the value inside the existing per-task CAS transaction, preserving user notes, email drafts and status. Missing `manualEffort` on status-only or legacy saves means *no change* to the stored estimate.

`assets/effort-planning.mjs` owns pure provenance-marked heuristics over **current structured analysis only**. `MANUAL/USER_SELECTED` indicates a selected band; `HEURISTIC/LOW` is a provisional guess. It offers display-only quick candidates where no source/QA gaps are present and does not alter `assets/task-rules.mjs` or the hard sprint/WRITE/signal/score/blocker priority order. Browser preview and editable band live inside the existing cards. Real task duration or efficiency gains remain unverified until human gold-case UAT.

See `docs/EFFORT_PRIORITIZATION.md` for exact branch order and limitations.

## v2.30: keyboard, focus and save status as safe, local presentation policies

`assets/focus-navigation.mjs` exports browser-policy helpers, independent of Jira source text: ignore shortcut events from text editors or modal, navigate solely through the existing filtered/sorted key list, restore disclosure/scroll/caret context using hashed headings, and sanitize persisted session data to issue keys and bounded numeric UI coordinates. `assets/dashboard.mjs` wires shortcuts `/`, `Alt+Up/Down`, `Alt+C`, `Ctrl/Cmd+Enter`, with a native keyboard guide inside the existing sidebar.

Each browser tab can remember its selected task and view; no raw notes, source excerpts, supplier IDs or PNR strings in view-state storage. The existing separate unsaved form storage/CAS is unaffected. Focused/detail editing prevents background DOM replacement; Save errors and CAS conflicts do not masquerade as success. The existing native batch-mail dialog restores opener focus when closed.

**Not yet proven:** actual screen-reader compatibility, keyboard conflicts under Windows language switch and browsers, long-running memory, real resume-time improvement. Behavioral unit tests cover pure policy only. See `docs/FOCUS_KEYBOARD_UX.md`.

## v2.31: snapshot-scoped high-throughput queue model

`assets/queue-performance.mjs` memoizes sorted queue by array object, filter output by normalized filter tuple, and each task's technical-rich search text with `WeakMap`. Explicit invalidation follows local manual-status save/overwrite; new snapshot arrays invalidate implicitly. Native debouncer coalesces 130ms query input, while keyboard Next/Previous flushes pending results. `filterTasks` retains its previous noncached behavior and an optional normalized-text provider with tested result parity.

`assets/dashboard.mjs` uses one delegated list click listener. Selected CSS/ARIA changes and dirty marker changes affect at most two DOM rows without list `innerHTML` rebuild; real filter/source changes still repaint the list to avoid unreviewed windowing/accessibility regressions.

`desk_store.py` provides `view_json_bytes()`, an immutable in-memory HTTP response cached by `(SQLite state_revision, import error)`. Each read checks the live database revision and, on miss, assembles payload and revision within one SQLite read transaction, guarding concurrency across separate Desk processes. `server.py` sends the cached bytes from original `/api/tasks`, using unchanged authenticated localhost/cloud/headers contract. Object consumers continue to receive independent `Desk.view()` dictionaries.

Timing evidence comes from `performance_smoke.py` and `queue_benchmark.mjs` with only synthetic 100/500/1000 issues. Neither evaluates real Chrome DOM layout, Windows laptop speed, human time or supplier correctness. See `docs/LARGE_QUEUE_PERFORMANCE.md`.

## v2.32: confidential local SQLite recovery and bounded snapshot watcher

`local_backup.py` uses SQLite's online backup API to create a standalone, consistent private DB under gitignored `backups/`; verifies PRAGMA integrity_check, minimum supported BA schema, SHA-256 + file size and a metadata-only manifest. The snapshot file is published before the manifest, so an interrupted backup is ignored; retention removes a manifest before its DB. No secrets or Jira rows in manifests or GitHub/public CI.

The local server holds `pipeline_lock(root/'.local-server')` for its full lifetime. Before Desk migrations on startup, an existing user DB is backed up if no valid backup newer than 24 h; a first-time DB is backed up after import. The watch thread checks the backup policy every 5 minutes and publishes only status metadata through existing authenticated /api/health. OFFLINE `restore_backup` must acquire the same server lock, verify filename/hash/schema, take a rescue backup, ensure no pending WAL traffic, stage verified SQLite content and atomically replace DB. This is not a browser or HTTP destructive action.

`snapshot_monitor.py` avoids processing unchanged successful source snapshots every 3 seconds, retries unchanged failed imports only after 30 seconds, and publishes generic diagnostic state without supplier logs/PII. The previous `Desk.import_snapshot` transaction, CAS state revision and Jira/Email read-only guarantees are unchanged. After server shutdown the watcher stop event is set, the port closes and the thread is joined.

Backups contain **DB saved state only**, not `data/`, uncommitted browser localStorage, external supplier downloads or Jira source evidence files. Windows ACL/BitLocker and real forced-crash/restore E2E remain untested until manual UAT. See `docs/PRIVATE_BACKUP_RESTORE.md`.
