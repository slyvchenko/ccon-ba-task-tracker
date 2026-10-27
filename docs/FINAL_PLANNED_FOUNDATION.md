# Завершальний пакет CSS / QA-13: технічний фундамент (v2.50.9)

## PERF-09: мінімальний cascade cleanup без редизайну

Залишено поточну структуру BA Desk. Із `assets/dashboard.css` прибрано дві точні дубльовані декларації: мобільні `min-height/height:140px` для редактора (основне правило вже застосовується на всіх ширинах) та пізніше повторне `text-align:left` для меню (те саме є в початковому правилі). Решта шрифтів, полів, media-query, focus-visible, forced-colors і reduced-motion не змінена.

`tests/css-cleanup.test.mjs` перевіряє відсутність цих дублікатів, збереження типографіки та базових accessibility guards; загальний Chromium E2E перевіряє, що сторінка не ламається. **НЕ доведено** screenshot parity на Windows Edge/Chrome при 320/380/750/1150/1700 px, zoom 200-400%, NVDA, forced colors. Цей human visual acceptance залишається відкритим.

## QA-13: незалежний локальний gold-gate, без вигаданих результатів

Використати лише приватне робоче середовище та **20-30 реальних Jira-кейсів**, заморожених до порівняння:

1. `python evaluation.py prepare --count 26 --root <PRIVATE_ROOT>`
2. Незалежний BA створює gold-очікування **до** перегляду candidate. Зафіксувати джерела, AND/OR, expected result, QA-позитивний/негативний/edge, статуси, supplier XML/REST та роль кожного факту. Заповнити існуючі `reviews.json` та заморозити `baseline_predictions.json`, `candidate_predictions.json`.
3. Локально створити `data/evaluation/gold_attestations.json` із **тільки приватними** рядками: `key`, `sourceFingerprint`, `referenceAuthorCode`, `independentReviewerCode`, `referenceFrozenAt`, `candidateFirstSeenAt`, `independentSourceReview: true`, `goldExpectedWritten: true`. Код рецензента має дорівнювати `reviewer` у відповідному рядку `reviews.json`, але бути іншим за автора gold.
4. `python qa13_gold_preflight.py --root <PRIVATE_ROOT>` повертає **лише агрегати**: кількість незалежних gold reference, review completion, заморожені predictions, відповідність рубрикам. Жодних case key, імен, source-text, email, URL, логів або raw scoring comments виводити не можна.
5. Навіть `READY_FOR_PRIVATE_HUMAN_SIGNOFF` **не означає PASSED**. Тільки незалежний BA / product owner після реальних перевірок підписує приймання поза GitHub. `humanAcceptance=NOT_RECORDED` у публічному реєстрі не змінюється.

**QA-13 PARTIAL:** інструмент локальної перевірки незалежності й замороження очікувань реалізовано, але реальні 20-30 gold оцінок і незалежний підпис у цьому PR **відсутні**. Публічний CI використовує виключно синтетичну когорту, не корпоративні Jira/PNR чи supplier ZIP.

Загальні критерії: `docs/BA_GOLD_CASE_ACCEPTANCE.md`. 
