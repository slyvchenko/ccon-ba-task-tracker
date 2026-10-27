# Історичні PR review-коментарі: реєстр і статус перевірки

Джерела: GitHub API `/pulls?state=all`, `/pulls/comments`, GitHub GraphQL review threads. Дані без приватних Jira/PNR/ZIP та без дослівних коментарів. Кожний запис має точний URL review, PR, шлях файла, коротку тему та статус.

**Базовий зріз:** 84 PR (злиті й закриті), 177 inline-коментарів, із них 148 початкових finding і 29 відповіді. Загальні conversation-коментарі, Codex/CodeRabbit summary і Issue #50 обліковуються окремо як контекст, а не як нові independent code findings. Після цього аудиту нові коментарі до наступних PR треба звіряти повторно.

**Важливо:** `thread_resolved=true` означає тільки натиснутий GitHub Resolve; `FIXED_IN_MAIN_PR_85` означає відповідний кодовий патч і synthetic CI, не людський UAT. Решту коментарів не можна маркувати DONE без індивідуального перегляду code path, тестів і рішення. Головне джерело: [повний machine-readable реєстр](PR_REVIEW_COMMENT_REGISTER.json).

## Вже виправлено (PR #85, 4/4 CI)

- [#80, evidence counter](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/80#discussion_r4386278998): generator/validator count complete code+test pairs consistently.
- [#22, unsafe symlink](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/22#discussion_r4369914398): fail closed on symlinked retention roots.
- [#32, SQLite rollback journal](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/32#discussion_r4371606800): do not overwrite before offline rollback-journal review.
- [#33, unsaved drafts](https://github.com/slyvchenko/ccon-ba-task-tracker/pull/33#discussion_r4372190236): over-capacity cannot silently truncate/destroy 101st draft.

## Порядок залишкової перевірки

1. P0/P1 security, data-loss, crash/restore, authorization and accurate BA fact claims. Тут без домислів щодо готовності: відкрити код і тест для кожної гіпотези.
2. P2 functional semantics and false-ready/false-done UX. Зберегти пріоритет active sprint і фактологічну точність.
3. P2 synthetic test fixture, documentation and refactoring remarks. Повторно не робити відхилених/deduplicated WIP PR.

Всі незалежні live BA/Windows acceptance gates лишаються у [Issue #50](https://github.com/slyvchenko/ccon-ba-task-tracker/issues/50). Не закривати без зовнішнього підпису.
