# Evidence-first BA workflow (local Codex + authorized Jira/Kibana browser)

**Mode:** your Windows computer, local CCON BA Desk and existing authenticated browser.
**Boundary:** read-only Jira, Kibana and supplier-log retrieval. The application
never modifies Jira/Confluence and never sends emails.

## Core work product: four outputs for every one of MY Jira issues

1. **Ready-to-use English task description.** Lead with the precise behavior to
   change. Include IF/THEN + AND/OR, affected method/field, concrete expected
   REST output, scope and essential acceptance only. No filler, no forced
   two-sentence limit. Extra paragraphs only for genuinely complex decisions.
2. **Prepared email draft** even if email is *not currently needed*: factual
   short supplier clarification/follow-up when required, otherwise an optional
   reusable email. Do not change `needsEmail` just because a draft exists.
   Do not invent recipients, method, confirmed delivery of email, log attachment
   or a speculative error. Normalize per `EMAIL_RULES.md` and keep user edits.
3. **Ready-to-download SUPPLIER-ONLY ZIP** if there is an authorized flow
   download and identifiable supplier. Include only the XML logs of the
   task's supplier; **never include REST, errors or other suppliers in the
   outgoing ZIP**. Keep the full original ZIP in private local storage for
   analysis, not for forwarding.
4. **Standard task context**: WHAT'S HAPPENING / WHAT TO VERIFY / NEXT STEP / WHY,
   with visible confidence, outstanding BA questions and references.
   Keep detailed log evidence and question history in collapsed sections of the original task page; no separate UI modes.

## Priority contract

1. All current **MY** issues in verified active sprint first.
2. Within each active-sprint / backlog lane: tasks needing supplier email
   (WRITE or verified `needsEmail=true`) before other actionable BA tasks.
3. Then other actionable tasks ranked by validated 0–100 factors; WAIT below
   actionable; manually DONE and inactive last.
4. The presence of an *optional drafted email* does not promote a task to WRITE.

## Full ZIP analysis vs supplier-only attachment

Input downloaded from CCON (example):
```text
download.zip
├── rest/
│   ├── request.json
│   ├── response.json
│   └── errors/
│       ├── 1-error.json
│       └── 2-error.json
└── supplier/
    ├── AirFranceKLM/
    │   ├── 1-...-request-body.xml
    │   └── 1-...-response-body.xml
    └── FinnAir/
        └── ...
```

**Investigation set for an AF/KL issue:** REST request/response + REST errors +
ONLY `supplier/AirFranceKLM/**`. Other suppliers are excluded. This applies
equally if there are 1 or 30+ error instances. Do not assume every request and
response is paired merely because filenames look similar.

**Attachment set:** ONLY `supplier/AirFranceKLM/*.xml`, packaged through the
existing verified `supplier_logs.py ingest` pipeline. Unlike analysis, this
archive intentionally excludes REST and error layers.

## Local Codex procedure (before BA interpretation)

1. `python jira_sync.py` refreshes your assigned tasks, descriptions, dates,
   comments and related Jira issues. Read `data/jira_context.json`.
2. `python kibana_evidence.py --root .` writes `data/kibana_evidence_plan.json`
   (up to 30 error examples per search). For a single task use
   `--issue CCON-123`. Open each approved Kibana link in the **current
   authorized browser session**, not via copied browser cookies/tokens.
   Some errors are ordinary discover links; others represent a group of
   10–30 instances. Filter and collect distinct failures by method,
   timestamp, error code, correlation and supplier.
3. `python supplier_logs.py plan --mode evidence --issue CCON-123`
   produces CCON download URLs for each valid cconFlowId **even if
   needsEmail=false**. The agent opens those URLs in the authorized
   browser and saves ZIP locally. Browser authentication is not
   available to these Python scripts; never pretend a planned URL
   was downloaded or parsed when it was not.
4. Run complete structural inspection of each full downloaded ZIP:
   `python layered_evidence.py PATH_TO_FULL_ZIP --supplier 'AF/KL' --issue CCON-123 --flow-id YOUR_UUID`.
   This saves a bounded JSON manifest in `data/evidence/CCON-123/`.
   It parses REST/selected supplier/errors and counts all matching files.
   It retains up to 40 structural examples per ZIP and summarizes errors.
   Original payload values remain in the private original ZIP.
5. For actual **value-level mapping** inspect the matching request/response
   files directly inside this local Codex run. Compare:
   - REST request → supplier request: parameter selection, transformation,
     missing values, whether request was sent at all
   - Supplier response → REST response: fields, segment/status updates,
     repeated elements, null/missing interpretation and errors
   - Errors folder → matching REST/supplier exchange and error handling
   - For 10–30 variants: categorize error code, method, exact stage,
     affected conditions, repetition and counterexamples
   Mark every inferred correlation/mapping as `CANDIDATE_ONLY` until actual
   values, identifiers and chronology support it.
6. Generate the **attachment separately**, from the same original ZIP:
   `python supplier_logs.py ingest --help` (follow exact command options
   shown there: root/key/flow/source). This writes an immutable original,
   normalized supplier XML files, facts.json and a supplier-only ZIP.
   The existing dashboard's "Завантажити ZIP" points only to that
   supplier-only archive. Check whether the right supplier and method are
   verified before treating the archive as safe to attach.
7. Compose ready task description, short context, factual email draft,
   precise BA questions and QA cases, citing the read Jira/Kibana/ZIP evidence.
   For unresolved sources say `UNAVAILABLE`, not `CONFIRMED`.
8. `python apply_analysis.py data/daily_analysis.json` validates and imports
   analyses, refreshes daily changes and now persists separate question
   records. Verify new/removed questions; **removed ≠ answered**.

## Verification states

- **CONFIRMED**: explicitly present in a read Jira comment, linked spec or
  inspected REST/supplier log.
- **CANDIDATE_ONLY**: correlation/path/type similarity, unverified mapping
  or hypothesis about the root cause.
- **OPEN / UNAVAILABLE**: ZIP or Kibana inaccessible, missing correlation,
  unknown supplier, incomplete request/response, or missing business rule.
- **READY_FOR_REVIEW** is not permitted while critical evidence is missing.

## Scope and limits

- Only your Jira-assigned tasks. Never broaden other people's work by
  discovering a shared Kibana error group.
- Never expose secrets, private payloads or real ZIPs in the public GitHub repo,
  model prompts, PR comments or CI logs.
- The automated ZIP parser intentionally stores metadata, structural field
  names, error codes and correlation candidates **not raw passenger data**.
  It does not claim to prove transformations without local full-payload review.
- Large or unfamiliar files, multiple suppliers, missing cconFlowId,
  archives needing sign-in and Kibana inaccessible in the browser are
  explicit blockers. Do not quietly substitute guessed values.
- The local Codex/Work task, not the Python server, controls browser navigation.
  The user must update the existing local Codex task from
  `DAILY_AUTOMATION_PROMPT.md`; merging GitHub code never updates the laptop.

## v2.8 refinement: one ZIP, two distinct deliverables

After downloading the authorized CCON full ZIP, use the `supplier_logs.py ingest` pipeline. It now also writes a privacy-bounded `data/evidence/CCON-KEY/FLOW.json` manifest; `valueReview` contains actual scalar **equality/mismatch checks** for paired REST and supplier exchanges. These are **CANDIDATE_ONLY**, not proven transformation errors. Raw field values and other supplier files are never persisted in that JSON manifest.

The downloadable ZIP in the existing dashboard is the **original supplier-only result**: XML files belonging to the one selected supplier, and never REST/error/other-supplier folders. `plan --mode evidence` permits packaging for active tasks even when no email is needed, including a manually completed item that still belongs to the current Jira scope.

Every analysis should produce a concise developer-ready English `standardDescription` when technically possible, and an optional editable `emailDraft` irrespective of `needsEmail`. A source-uncertain fallback draft must not pretend a supplier method or attachment has been verified.

## v2.9: серійний Kibana error investigation (офлайн-етап локального Codex)

**Цей скрипт сам не відкриває браузер/Kibana, не виконує HTTP-запит і не підтверджує live availability.** Локальний Codex відкриває лише дозволені Jira/Kibana URLs у вже авторизованому браузері, обирає до 30 *різних* flow за конкретним кодом помилки, завантажує повні ZIP через CCON і готує `data/evidence/CCON-123/<flow>.json` за допомогою `supplier_logs.py ingest` або `layered_evidence.py`.

Далі запуск:

```bash
python error_series.py --issue CCON-123 --error-code AF_REJECTED --max-cases 30
```

Вихід **`data/investigations/CCON-123.json`**: кількість унікальних flows, покриття REST/supplier/errors, групи code+method, зв'язки із source flow IDs, candidate mismatches, можливі причини та альтернативи, конкретні докази, яких бракує. Повторні експорти одного flow не збільшують кількість випадків. Інший supplier чи інша Jira-задача не потрапляють у дослідження. Якщо в error-search є 100+ випадків, звіт не вдає, що 30 детермінованих flows є репрезентативною вибіркою.

Статус **`ROOT_CAUSE_UNCONFIRMED`** зберігається завжди, доки немає окремого експертного підтвердження з raw REST/Supplier RQ/RS, mapping/spec та контрприкладами. Помилка в supplier response **не** доводить, що supplier винен: CCON міг надіслати некоректний RQ. Усі висновки подаються як гіпотези з альтернативою й планом перевірки.

Серійне дослідження входить у наступний model-based BA аналіз через `errorSeriesInvestigation` (скорочений safety-bounded snapshot) і в існуючу згорнуту секцію доказів у dashboard. Всі ZIP та персональні дані залишаються тільки локально.

## v2.10: локальний browser-to-ZIP handoff

**Python не входить у Kibana і не отримує cookies/tokens.** Локальний Codex/Work відкриває CCON downloadUrl у вже авторизованій сесії браузера, перевіряє фактичний файл та зберігає ZIP в точний локальний шлях.

1. Після Jira sync запусти `python local_downloads.py prepare --issue CCON-123` (без `--issue`: всі активні твої задачі). Читай приватний `data/browser_handoff.json`: у ньому є issue, flow, supplier, Kibana URL, CCON downloadUrl, cached і saveAs.
2. Для cached=false відкрити тільки наведений downloadUrl в авторизованому браузері. Browser download capture повинен повернути справжній ZIP, який треба зберегти в точний saveAs, наприклад `downloads/ccon/CCON-123/11111111-2222-4333-8444-555555555555.zip`. ERR_ABORTED під час навігації можливий, але сам по собі не доводить завантаження.
3. `python local_downloads.py process --issue CCON-123` обробляє лише ці локальні ZIP. Перевіряє Jira fingerprint, дату, розмір, ZIP header, постачальника; готує **supplier-only ZIP** для листа та **окремий REST/errors/supplier** evidence manifest.
4. Перевір `data/download_handoff_status.json` і звичайний блок «Логи до листа»: по flow видно READY/PENDING/PARTIAL/STALE/NEEDS_REVIEW/FAILED/BLOCKED та причину. НЕ вважай PENDING або NEEDS_REVIEW готовим без перевірки.
5. Не переносити браузерні cookies/token чи приватні ZIP у GitHub. Повний ZIP залишається локально, вихідний архів містить **тільки supplier XML вибраного постачальника**, без REST/errors/інших suppliers.

Сам `prepare` не завантажує файл. Без чинної авторизації/використання браузера залишити чесний статус і причину. Синтетичні CI тести не є live Kibana UAT.

## v2.13: Method / Contract shape і timeline одного flow

Після локального `supplier_logs.py ingest` або `layered_evidence.py` у приватному JSON з’являється `flowDiagnostics`. Це два окремі результати:
- **Контрактні кандидати**: напрям REST request → supplier request / supplier response → REST response, назва нативного supplier method із підтвердженого імені XML, кількість полів, `null` та повторювані масиви/XML-елементи, збіги/розбіжності зі `valueReview`. REST endpoint **не вигадується**, якщо його немає в джерелі; результати мають стан `CANDIDATE_NOT_CONFIRMED_CONTRACT`.
- **Події в часі**: порядок лише за явно прочитаними offset-aware ISO timestamp у ZIP payload (наприклад `timestamp`, `eventTime`, `createdAt`). ZIP order, останній modified time, supplier sequence і номер файлу **не є** часовими мітками. Якщо timestamp відсутній або в одному файлі кілька різних моментів, статус явно неповний/неоднозначний. Повторний метод означає лише можливість retry.

Інші постачальники і значення PNR/пасажирів не включаються в результат. Для спірного mapping перевіряти raw ZIP тільки у локальному Codex разом із підтвердженим supplier/API контрактом і Jira-вимогою. Серія не доводить причину бага автоматично. Вихідний ZIP для листа як і раніше містить **тільки XML вибраного supplier**.

Для підтвердженої хронології Kibana потрібні подієві timestamps конкретного flow, а не час ZIP. Без них звіт залишається неповним.
