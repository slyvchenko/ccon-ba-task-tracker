# QA-13: приватне незалежне BA-приймання (20–30 кейсів)

Це **інструмент перевірки повноти анкет**, не заміна реального BA review. Синтетичний CI не підтверджує фактів Jira, supplier/XML/REST, людської якості опису, правильність адресата або реальне схвалення релізу.

## Протокол

1. Виберіть 20–30 справжніх задач **лише у затвердженому приватному середовищі**. Для стандартної когорти 26: READY 4, WRITE 5, WAIT 4, DECIDE 4, DEEP 5, ERROR 4. До перегляду AI-output незалежно заморозьте еталонні факти/умови/QA та джерела.
2. Людина оцінює кожну задачу: accuracy фактів, логіку AND/OR і handoff, критичні false-ready, самовільну зовнішню дію, вигадані source/recipient. Фіксує фактичний час до наступної дії (TTNA) і до handoff draft (TTSH).
3. Створіть **локальний JSON поза GitHub-репозиторієм**, який містить лише псевдоніми `GOLD-01..GOLD-30`, категорії, булеві рішення та числа. Жодних PNR, Jira-key, email, персональних імен, URL, документів, ZIP або тексту кейса. Приклад структури **одного синтетичного** запису:

```json
{
  "id": "GOLD-01",
  "archetype": "READY",
  "referenceFrozenBeforeAI": true,
  "independentReview": true,
  "sourceAccessVerified": true,
  "facts": "PASS",
  "rules": "PASS",
  "handoff": "PASS",
  "criticalFalseReady": false,
  "unapprovedExternalAction": false,
  "falseSourceOrRecipient": false,
  "result": "PASSED",
  "ttnaSeconds": 5.4,
  "ttshSeconds": 19.2
}
```

Повний JSON: `{"schemaVersion":1,"cases":[...26 entries...]}`. У реальному оцінюванні поля must match schema, не вигадуйте `PASS`, якщо джерела недоступні. Використовуйте `BLOCKED`/`INCONCLUSIVE`.

## Створення безпечної порожньої анкети (v2.50.10)

Для 26 незалежних кейсів не потрібно вручну писати всю структуру JSON. Згенеруйте **порожню, заблоковану анкету** у приватній папці **поза репозиторієм**:

```powershell
python private_gold_template.py --output "C:\\<private-folder>\\gold-review.json" --confirm "CREATE EMPTY PRIVATE GOLD COHORT"
```

Цей крок потребує явної згоди й не перезаписує наявні файли. Файл містить лише `GOLD-01..GOLD-26` і розподіл READY 4, WRITE 5, WAIT 4, DECIDE 4, DEEP 5, ERROR 4. Усі результати спочатку **BLOCKED / INCONCLUSIVE**; прапорці незалежної перевірки та підтверджених джерел `false`, часові виміри `null`. `false` в полях критичних ризиків означає **лише незаповнений шаблон**, а не підтверджену відсутність інциденту. Це гарантовано **не** пройде readiness-перевірку без ручного заповнення.

На кожному реальному кейсі незалежний BA в дозволеному приватному середовищі має вручну вказати перевірені рішення й виміри. Результати не вивантажуйте до GitHub, не додавайте Jira/PNR/імена/емейли до JSON. Для підсумку локально запустіть `python private_gold_review.py --input "<private-folder>/gold-review.json"`. Навіть повністю заповнений валідний JSON **не** означає автоматичне затвердження релізу.

## Локальний запуск

```powershell
python private_gold_review.py --input "C:\<private-review-folder>\gold-anonymous.json"
```

Програма **лише читає** анкету й друкує агрегати: архетипи, результати, кількість незалежно оцінених кейсів, критичні порушення, середні TTNA/TTSH. Текст кейса, псевдоніми, URL та шлях файлу не показуються. Немає автоматичного збереження, мережевих викликів, Jira update або листів. Неповна або приватна/невірна структура зупиняє розрахунок без друкування вмісту.

Навіть за 26 синтетичними успішними результатами JSON містить `humanAcceptance: NOT_RECORDED` і `releaseApproved: false`. `criteriaReadyForHumanDecision=true` означає лише, що анкета пройшла обмежений формальний контроль, а **не** реальну якість або підпис. Єдиний source of truth для схвалення: приватно збережене незалежне людське рішення і Issue #50.

**Не змінювати** `human_acceptance` в `docs/BACKLOG_ACCEPTANCE_LEDGER.json` або `QA-13` на IMPLEMENTED без 20–30 незалежно оцінених реальних задач. Див. також `docs/BA_GOLD_CASE_ACCEPTANCE.md`.
