# CSS and visual regression cleanup, v2.38

## Source-audited deletions, not a redesign

The old task metadata row (`.task-badges`, `.signal-strip`, `.signal-text` and text-tone aliases) was replaced by provenance-labeled `.task-meta-compact` in #35. A grep across `dashboard.html` and `assets/dashboard.mjs` on v2.37 found **zero runtime uses** of the removed class names. PR #38 deletes only these orphan declarations (including legacy mobile overrides), not the original AERTiCKET brand, current signals, QA gate, email panel, task cards, fonts or grid.

The stylesheet had 1524 lines before this small cleanup. Some repeated selectors are **legitimate responsive overrides** under distinct media rules; deleting them by simple deduplication could break Windows 400% zoom or keyboard focus. We do **not** claim all CSS duplicates were safely consolidated.

## Browser verification

The opt-in Playwright synthetic Chromium suite now records screenshot artifacts at **320 / 768 / 1440 CSS px**, checks that `#detail` / queue remain visible and checks global horizontal overflow stays within 2px rounding. It also exercises keyboard/focus, CAS and recovery from previous releases. Screenshots contain **only synthetic test tasks**, retained temporarily in Actions; no production source/PNR/emails. CI geometry checks are useful regression indicators, **not pixel-perfect visual diffs** against an approved Windows screenshot baseline.

A human operator should compare old vs new Windows Chrome/Edge on the same device, DPI, zoom (100%, 200%, 400%), font availability, colors, task archetype (READY/WRITE/WAIT/BLOCKED/deep evidence) and confirm:
- same familiar left queue / right detail design, same scrolling and position restore
- no hidden Jira status vs manual state, blocker, stale/CAS error or unverified copy warning
- keyboard controls remain visible, and long REST/JSON/code content does not create unexpected page overflow
- native 400% zoom/320px, screen reader and Windows high contrast remain usable

## Why no complete CSS overhaul yet

Rewriting all ~1500 lines of responsive CSS in one PR would increase regression risk without production screenshots. #38 intentionally performs a small, verifiable dead-style cleanup and adds browser artifact evidence. Any further formatting/token/cascade consolidation should be done **after** the human visual UAT and can be incorporated into #47 if concrete defects are observed.

## Next backlog

See `docs/BACKLOG_CLOSEOUT_PLAN.md` for the whole 129-row inventory and recommended **10 additional scoped PR (#39–48)** for the local product, plus mandatory independent gold-case/Windows UAT. Deferred cloud P3 features are not implicitly accepted.

## PR #58 (v2.49.3): технічні поля і repeatability-baseline

- Без зміни бренду чи двоколонкової архітектури технічні поля **IF / THEN** отримали семантичний `code.technical-token` з `overflow-wrap:anywhere` і `white-space:pre-wrap`. Значення PNR, `SegmentRefID`, `DeliveryStatusCode` і REST-ідентифікаторів не обрізаються, не скорочуються й не змінюються у вихідному тексті. CSS також дозволяє переносити довгі значення в таблицях доказів, але зберігає локальну прокрутку `.evidence-scroll` для складних таблиць.
- Безпечна CSS-консолідація: канонічний `.row-title` тепер має фінальне значення margin без другого дубльованого правила; перший `.row .badge` більше не містить трьох властивостей, які одразу перекривалися іншим правилом. Адаптивні media query (320/750/1150/1700) та стилі forced colors навмисно **не об'єднували**.
- Synthetic Chromium для **320 / 768 / 1440 px** перевіряє точність `textContent` довгих технічних полів, відсутність горизонтального переповнення, незмінність відкритих секцій та стабільність геометрії брифінгу й токенів (до 2 px). CI зберігає PNG **до та після перезавантаження** і SHA-256 обох зображень для ручного diff. Байтову рівність PNG навмисно **не** використовуємо як автоматичний gate через нестабільність растеризації Chromium. Це синтетична structural/semantic regression, не затверджений pixel baseline проти попереднього релізу.
- Потрібне незалежне порівняння скріншотів `main` до/після на Windows Chrome/Edge, DPI і 100/200/400% zoom, перевірка реальних довгих supplier/REST trace, незалежне схвалення стилю/бренду. Не проголошувати UI-08 чи UI-10 `IMPLEMENTED` або human-approved без цього доказу; обидва залишаються `PARTIAL`.
- Всі 129 вимог збережено. Немає змін у серверній схемі, алгоритмі пріоритетів, ручних Jira/email діях, локальних даних, копіюванні та експорті.

## PR #69: безпечна консолідація глобальних CSS-правил

- Зведено до одного глобального блоку `.row-title` (не втрачаючи `-webkit-line-clamp:2` та `overflow-wrap:anywhere`), `.row .badge` (незмінні `font-size:10px`, `font-weight:400`), і глобальний `.row` `min-width:0`.
- Об'єднано базові стилі `.email-panel textarea` (розмір, шрифт, висота, колір). **Адаптивний @media 750px із власною висотою залишено недоторканим**. Усунуто один повністю повторний `text-align:left` для меню, зберігши його у базовому блоці.
- Код зменшено з 1528 до 1520 рядків без зміни кольорових токенів, структури HTML, JSX/JS, grid, focus outline, high-contrast, reduced-motion, статусів або порядку media rules. Статичний Node contract перевіряє один глобальний селектор, повний email-font contract і присутність адаптивних/a11y правил.
- Немає затвердженого **cross-release pixel baseline**. Не можна вважати цей маленький безпечний крок повним переписуванням каскаду. PERF-09 лише `PARTIAL` до незалежного Windows Chrome/Edge DPI/100–400% screenshot diff, NVDA/high contrast і людського signoff. Повторення `@media` та пізніх бренд-override правил можуть бути **навмисними**, тому їх не видалено механічно.

## v2.50.10: canonical brand tokens, no visual redesign

Consolidated duplicate global `:root`, `header`, `.primary`, `.primary:hover`, and `.row.selected` overrides into their existing canonical declarations. The final computed AERTiCKET-inspired color tokens, background, spacing and selected states remain unchanged. Existing media-query and forced-color overrides remain in their original order. A Node regression verifies exact canonical values and selector uniqueness, alongside the existing Chromium responsive and accessibility suite. Native Windows visual diff and real-brand approval are **still not recorded**; `PERF-09` remains PARTIAL.
