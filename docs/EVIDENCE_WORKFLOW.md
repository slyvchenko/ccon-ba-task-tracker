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
4. **Quick context**: WHAT'S HAPPENING / WHAT TO VERIFY / NEXT STEP / WHY,
   with visible confidence, outstanding BA questions and references.
   Make the long technical investigation available under "Глибокий аналіз".

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
