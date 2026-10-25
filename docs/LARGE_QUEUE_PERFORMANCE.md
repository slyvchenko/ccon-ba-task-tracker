# v2.31: великий BA backlog, локальна швидкодія та відтворювані заміри

**Статус:** оптимізації закодовані й перевіряються в CI. Наведені SLO є цілями, а не виміряними Windows результатами. Жодні корпоративні Jira, REST/XML, PNR чи email дані не потрапляють у тести.

## Що саме прискорено

1. **Пошуковий індекс за snapshot.** `assets/queue-performance.mjs` обчислює normalized/Unicode-folded текст лише для задач, які проходять дешеві фільтри й реально беруть участь у пошуку. Зберігає текст `WeakMap(task)` і повторно використовує під час наступних запитів. При новому JSON/snapshot або ручній зміні статусу кеш інвалідовується. Збіги мають збігатися **точно** із попереднім `filterTasks`, включно з AND усіх введених слів і без втрати технічних полів.
2. **Кеш ранжування.** `rankTasks` виконується один раз на змінений масив задач або ручний save, а не на кожен re-render. Ні effort estimate, ні cache не змінюють sprint→genuine WRITE→signal→queueScore→blocking або Jira-read-only.
3. **Debounce вводу.** Пошук запускається через ~130 ms після останнього символу. Інші фільтри оновлюються відразу; навігація з клавіатури примусово застосовує pending пошук, щоб не показати застарілий список.
4. **Менше DOM-роботи.** Єдиний делегований click listener замінює по listener на кожний рядок. При виборі задачі оновлюється лише стиль selected/aria-pressed двох рядків, а не HTML всієї черги. При наборі нотаток змінюється лише unsaved-dot однієї задачі. Повний HTML списку залишається при справжньому оновленні/фільтрації, без ризикованої віртуалізації до browser profiling.
5. **Серверний JSON cache.** `Desk.view_json_bytes()` віддає bytes response з кешу лише коли `state_revision` та `error` збігаються. Перевірка revision і повне збирання відбуваються у **одній SQLite read transaction**, щоб паралельний процес не породив несумісний номер ревізії й тіло. Після CAS manual save, import, duplicate/error snapshot, зміни іншого Desk екземпляра кеш автоматично відновлюється. Для не-HTTP споживачів `Desk.view()` як і раніше повертає незалежний dict без спільного mutable кешу. `/api/tasks` формат і auth/CSP не змінилися.

## Synthetic benchmarks, які можна повторити локально

```bash
python performance_smoke.py --sizes 100 500 1000 --iterations 25
node queue_benchmark.mjs --sizes 100 500 1000 --iterations 25
python check_project.py
```

- **Python** звітує p50/p95: `Desk.view()` (dict), `Desk.revision()` (single row), `Desk.view_json_bytes()` (cached immutable bytes) і розміри відповіді. Немає мережі або рендерингу.
- **Node** звітує p50/p95 для незакешованого пошуку, cold search з rebuild та warm repeated-index search. Порівнює результати пошуку перед/після на 100/500/1000 синтетичних BA payloads. Немає DOM і Chrome. Не порівнюйте p95 різних машин або холодне/warm як еквівалентні маршрути.
- **CI** запускає короткий синтетичний benchmark лише як smoke і друкує заміри у логах. Не встановлюємо жорсткий timeout за milliseconds на спільних GitHub runners; ці runners не є Windows комп'ютером аналітика.

### Реальний браузерний profiling (ще не виконаний)

На Windows (назва ноутбука/CPU/RAM/режим живлення, браузер і версія) підготуйте 100, 500 і 1000 *синтетичних* задач, у Chrome/Edge DevTools Performance заміряйте:
- Cold load → перший взаємодійний рядок; warm повторне відкриття; scripting/layout/paint breakdown, peak heap.
- Введення поля пошуку (перший та останній символ), фільтр sprint/WRITE, видалення пошуку, `Alt+Up/Down`, Save, DONE→Next.
- Зміна Jira snapshot під час редагування глибокого кейсу; чи зберігається DOM фокус, caret, секції, scrolling, dirty form і CAS-протокол.
- 8-годинну сесію: heap snapshots на початку/кінці, listener leak, CPU idle, correctness у двох вкладках.
- 200%/400% zoom, screen reader, Windows high contrast, narrow viewport.
- Repeat 20 разів з та без навантаження; занотувати p50/p95, missing-match count, помилки статусів, фактичний time-to-handoff. Результати з корпоративними даними зберігайте тільки у захищеному приватному середовищі.

## Технічна межа й next steps

**Не реалізовано:** віртуалізацію тисяч DOM rows. Кожен рядок має змінну висоту, групові заголовки та клавіатурний focus; наївне windowing може приховати поточну задачу/ARIA й зламати `Alt+Up/Down`. Спочатку зафіксуйте реальний DevTools профіль, а потім обирайте доступну windowing стратегію й браузерні E2E перевірки.

**Не claim:** реальне скорочення часу роботи, Chrome p95, 8h memory stability, UAT або бізнес-правильність з проходження CI. Код не виконує Jira edit і не надсилає листів. Під час падіння бази/браузера існуючі ручні SQLite notes/draft і CAS версії лишаються окремим захистом.

**Гейт для #31:** Python/Node unit tests + release/Compose pass; exact search/order parity on 100/500/1000 synthetic tasks; bytes-cache invalidation across two Desk instances and failed import; no private data in test fixtures; browser timing remains a tracked UAT gate, not false `DONE`.
