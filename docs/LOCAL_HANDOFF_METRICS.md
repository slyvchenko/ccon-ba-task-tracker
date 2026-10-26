# Локальні BA-метрики без передачі даних (v2.50.6)

**PRIOR-07:** вимірюйте час від початку роботи над задачею до готової передачі іншій стороні. Час вводиться **вручну в секундах після фактичного handoff** за одним із фіксованих типів: `ERROR_TRIAGE`, `SUPPLIER_QUESTION`, `REBOOKING`, `REFUND_REISSUE`, `API_ANALYSIS`, `EMAIL_HANDOFF`.

```powershell
python local_handoff_metrics.py handoff --archetype ERROR_TRIAGE --seconds 540 --confirm "SAVE LOCAL BA METRIC"
python local_handoff_metrics.py summary
```

**PRIOR-08:** можна вручну відзначити неправильний пріоритет без запису Jira ID. Виберіть початковий і виправлений діапазон (`LOW`, `MEDIUM`, `HIGH`) та одну причину (`IMPACT`, `URGENCY`, `DEPENDENCY`, `EFFORT`, `STALE_CONTEXT`).

```powershell
python local_handoff_metrics.py correction --from-band LOW --to-band HIGH --reason URGENCY --confirm "SAVE LOCAL BA METRIC"
python local_handoff_metrics.py summary
```

Дані зберігаються лише локально у `data/private_metrics/handoff_aggregate_v1.json`, в агрегованій формі: кількість, сума тривалості за категоріями та кількість виправлень. **Не зберігаються** окремі події, task ID, текст, ім'я, PNR, email, timestamp, supplier trace чи вміст бази. Немає мережевих викликів, хмарних метрик, автоматичного збору, фонових задач або перенавчання пріоритетів. Офіційна черга задач не змінюється. Порожній `summary` нічого не створює.

Для запису потрібне точне підтвердження; запис атомарний. На POSIX використовується файл mode 0600 і приватна директорія mode 0700. На Windows безпека NTFS ACL залишається `UNVERIFIED`, її потрібно перевірити окремо. Вміст директорії `data/` не входить до релізного ZIP чи Git.

**Межі:** ці метрики є ручною вибіркою, а не автоматичним заміром від старту до передачі; вони не доводять фактичний p95, розподіл за реальними завданнями чи покращення продуктивності. PRIOR-07 і PRIOR-08 залишаються `PARTIAL` до незалежного BA/UX приймання та перевірки на реальній роботі. Схему корекції пріоритетів не застосовувати для автоматичного сортування.
