# CCON BA Desk: функціональна архітектура та потік однієї задачі

Статус: 2026-10-24. **Суцільні вузли = реалізовано в PR-гілці**,
**пунктирні = цільова хмарна архітектура (ще не розгорнута)**.
Цей документ описує функції коду, а не гарантує фактичний доступ до Jira,
логів, Work/Codex або корпоративної хмари.

## 1. Повний task lifecycle (фактичний)

```mermaid
flowchart TD
  A["Jira read-only sync<br/>jira_sync.py"] --> B{"JQL: assigned, not Done,<br/>not Epic"}
  B -->|included| C["Description + all comments<br/>linked issues + metadata"]
  B -->|excluded| X["Outside query / previously saved archive<br/>NOT automatically completed"]
  C --> D["Configured board active sprint<br/>sprint_priority.py"]
  D --> E["Atomic context + snapshot<br/>storage.py, pipeline_lock.py"]
  E --> F{"Context fingerprint<br/>unchanged?"}
  F -->|yes| G["Prior analysis can remain current"]
  F -->|no| H["Old analysis marked STALE"]
  G --> I["Work/Codex agent: read rules<br/>DAILY_REVIEW.md, BA_DEEP_REVIEW.md"]
  H --> I
  I --> J["Evidence and history<br/>confirmed vs uncertain"]
  J --> K["BA dossier: overview, current/target,<br/>scope, conditions, questions, QA"]
  K --> L["Outputs: Jira draft, email draft,<br/>next action, queue score 0..100"]
  L --> M{"Need supplier log<br/>and cconFlowId?"}
  M -->|yes| N["LOG_WORKFLOW.md<br/>supplier_logs.py: ZIP/XML"]
  M -->|no| O["apply_analysis.py"]
  N --> O
  O --> P{"All issues covered,<br/>fingerprints valid, schema valid?"}
  P -->|no| Q["Reject import;<br/>preserve previous state"]
  P -->|yes| R["SQLite + immutable manual state<br/>desk_store.py"]
  R --> S["Delta report + quality warnings<br/>review_report.py"]
  S --> T["Dashboard + source-linked<br/>briefing and filters"]
  T --> U["BA decides, copies and<br/>edits locally"]
  U --> V["Jira/Confluence/email never<br/>changed by the analysis pipeline"]

  classDef risk fill:#fff3d4,stroke:#b88429,color:#553a11
  classDef stable fill:#e4f3f9,stroke:#2185ad,color:#154562
  classDef output fill:#e8f3e5,stroke:#458f68,color:#21513a
  class B,F,M,P,Q,X risk
  class A,C,D,E,G,H,I,J,K,L,N,O stable
  class R,S,T,U,V output
```

**Important distinction:** the dashboard lets the user manually save local
status/notes/edited drafts, and Outlook actions can open mailto drafts.
Neither is an automatic Jira write, but the latter is Windows-specific
and not suitable as the cloud outbound-mail pattern.

### Important scope boundary

The current JQL filters `assignee = currentUser()`. Active sprint
membership is fetched from the authoritative board, but **only
assigned issues already in this JQL** become analyzed task cards.
A future all-sprint/team queue must be an explicit product decision
and not inferred from verified membership alone.

## 2. Module catalogue and ownership

| Module | Current job | Input/output | Cloud or product decision |
| --- | --- | --- | --- |
| `jira_sync.py` | Jira API search, pagination, comments, dependencies, stale fingerprint | Jira → context/snapshot JSON | Keep; split fetch and source-normalization; read-only OAuth/secret |
| `sprint_priority.py` | Board-specific verified active sprint membership | Jira Software Agile → per-task lane | Keep; configure `CCON_JIRA_BOARD_ID` or local `.jira-board.json` |
| `configure_jira.py` | Interactive Windows Jira credential setup | DPAPI local secret | Legacy only; cloud must use managed secret |
| `ROVO_PROMPT.txt` | Manual alternate snapshot creation | Rovo → inbox JSON | Deprecate as primary; retain explicit offline fallback |
| `DAILY_REVIEW.md` | Work/Codex orchestration instructions | source + rules → analysis | Keep until cloud worker replaces Work dependency |
| `DAILY_AUTOMATION_PROMPT.md` | Existing scheduled task prompt | local agent instruction | Keep as legacy adapter; cloud schedule separate |
| `BA_ANALYSIS_RULES.md` | Factual review / unresolved questions | Jira context → rationale | Keep as controlled rules |
| `BA_DEEP_REVIEW.md` | Dossier, provenance, IF/THEN, readiness | evidence → `briefing` | Keep with grounded evaluations |
| `TASK_DESCRIPTION_RULES.md` | English CCON Task description | verified rules → draft | Keep; acceptance traceability |
| `EMAIL_RULES.md`, `email_rules.py` | Compose/normalize supplier drafts | analysis + verified method → draft | Keep drafting only; no automatic send |
| `LOG_WORKFLOW.md`, `supplier_logs.py` | Find cconFlowId, sanitize/inspect XML, archive | referenced flow + authorized ZIP → local archives | Separate background evidence worker; encrypted object storage |
| `log_attachments.py` | Validate ZIP integrity, serve/download, Windows folder | logs index → task assets | Keep download; remove Windows folder opener from cloud |
| `apply_analysis.py` | Coverage/fingerprint/shape validation + import | analysis JSON → task snapshot | Keep and expand quality gates |
| `ba_briefing.py` | Structured briefing shape and diagnostic warnings | analysis.briefing → checks | Keep; validate sources semantically using human eval |
| `review_report.py` | Daily task/question changes and warnings | previous + current → delta JSON | Keep, improve actual Jira Done tracking |
| `desk_store.py` | SQLite manual status, notes, drafts, task cache | snapshot ↔ DB | Keep interface; migrate storage to PostgreSQL for cloud |
| `schema.py` | Validation types, score range 0–100, safe URLs | payload → validated | Keep |
| `storage.py`, `pipeline_lock.py` | Atomic JSON and cross-process lock | local files | Replace in cloud with transaction/lease/object store |
| `server.py` | Localhost HTML, JSON API, manual saves, attachment download | browser ↔ local files | Rewrite auth/storage boundaries before internet exposure |
| `dashboard.html`, `assets/dashboard.mjs` | BA queue, detail, briefing, local forms and mailto | API → browser | Keep UI concept; cloud auth, role checks, autosave |
| `assets/task-rules.mjs` | Pure sorting, signals, filtering and manual overrides | task objects → ordered tasks | Keep sprint-first rule with tests |
| `assets/logs.mjs` | Log status/update client | task ZIP catalog | Keep download pattern |
| `assets/dashboard.css` | UI/theme | design tokens | Use AERTiCKET-inspired brand tokens pending official sign-off |
| `evaluation.py` | Local 20–30 real-case human quality evaluation | frozen context + A/B ratings → metrics | Keep data off public GitHub |
| `app_config.py` | Shared constants/paths/version | runtime config | Cloud configuration must be environment-based |
| `Start CCON BA.bat` | Windows launcher | local shell | Legacy only; remove from cloud deployment image |
| `build_release.py`, `release_manifest.json` | Local ZIP release packaging | source → ZIP | Keep for Windows fallback only |
| `check_project.py`, `tests/`, `.github/workflows/quality.yml` | Regression, syntax, independent release checks | PR → pass/fail | Keep; mandatory PR check + cloud security checks |

## 3. One-task interactions (sequence)

```mermaid
sequenceDiagram
  autonumber
  participant J as Jira Cloud (read-only)
  participant P as Sync / sprint probe
  participant S as Snapshot / database
  participant A as Work/Codex analyst
  participant Q as Quality & delta review
  participant U as BA dashboard
  P->>J: GET assigned issues + all comments
  J-->>P: Text, links, timestamps
  P->>J: GET active board sprints + all sprint issues
  J-->>P: Verified sprint keys
  P->>S: Atomic context and task snapshot
  S-->>A: Prior notes + fingerprints + new context
  A->>A: Fact check, timeline, IF/THEN, QA
  A->>S: Local analysis.json (no Jira mutation)
  S->>Q: Schema + fingerprint coverage
  alt invalid or stale
    Q-->>A: Reject, preserve prior approved data
  else valid
    Q->>S: Import new analysis, preserve manual state
    Q->>U: Changes/questions/warnings
    U-->>U: User reviews recommendation and drafts
  end
```

## 4. Target cloud architecture (NOT IMPLEMENTED)

```mermaid
flowchart TD
  U["Business Analyst browser"] --> ID["Company SSO / OIDC + MFA"]
  ID --> GW["Private authenticated HTTPS application gateway"]
  GW --> API["BA Desk Web/API service<br/>cloud container"]
  API --> DB[("Managed PostgreSQL<br/>manual state + task metadata")]
  API --> OBJ[("Encrypted private object storage<br/>evidence, snapshots, ZIP")]
  SCH["Cloud Scheduler<br/>08:00 Europe/Warsaw"] --> QUEUE["Job queue + idempotency"]
  QUEUE --> WORK["Read-only Jira + evidence ingestion worker"]
  WORK --> JIRA["Jira Cloud<br/>read-only scope"]
  WORK --> OBJ
  WORK --> AGENT["Approved model / analysis worker"]
  AGENT --> VALID["Evidence checks + frozen prompt version<br/>evaluation gates"]
  VALID --> DB
  VALID --> OBJ
  SECRETS["Managed Secret Store<br/>no GitHub tokens"] --> WORK
  SECRETS --> AGENT
  AUD["Audit logs, alerts, failed-run dashboard"] --- WORK
  AUD --- API
  GH["GitHub PR CI / regression checks<br/>NO production Jira data"] -.-> API

  classDef proposed fill:#e5effb,stroke:#587ead,color:#1b3e6e
  class U,ID,GW,API,DB,OBJ,SCH,QUEUE,WORK,JIRA,AGENT,VALID,SECRETS,AUD,GH proposed
```

Cloud deployment **requires an approved corporate infrastructure account,
SSO tenant, runtime model access, data-retention policy and Jira read-only credentials**.
The existing 127.0.0.1 server has no remote user authentication and cannot
safely be publicly exposed or served by GitHub Pages alone.

## 5. Product removal / refactoring plan

| Decision | Module / feature | Why |
| --- | --- | --- |
| KEEP | Jira read-only sync, QA dossier, source references | Core analyst value |
| KEEP + HARDEN | Per-task delta report and quality warnings | Must not mistake leaving JQL for Jira Done |
| KEEP + PRIORITIZE | Active sprint lane and 0–100 score | Scrum scope outranks every backlog score |
| REWORK | Old shared flat priority, stale state, previous manual choices | Need explicit sprint and completion provenance |
| REWORK | Work/Codex dependency | Cloud worker needs approved model runtime, retries, stable prompt version |
| REWORK | Prompt self-improvement | Daily suggestions + bounded adaptive checklist, validated promotion only |
| REWORK | Local SQLite and ZIP | Multi-device private cloud needs transactions, encryption, backups |
| REMOVE FROM CLOUD (KEEP LEGACY) | `Start CCON BA.bat`, Windows folder opener, DPAPI file | Windows-specific |
| REMOVE FROM CLOUD (KEEP FALLBACK) | Rovo manual JSON snapshot | Duplicate source of truth vs Jira read-only sync |
| REMOVE FROM CLOUD | Bulk mailto Outlook launch | Not a safe cloud-native draft synchronization mechanism |
| ADD | OAuth/SSO, role restrictions, tenant/user isolation | Internet-accessible task/context data |
| ADD | State transition audit, Jira Done verification, run health | No silent false completions or missing data |
| ADD | Versioned prompt experiments and approval gate | Avoid daily degradation and unsupported assertions |
| ADD | Design system and accessible cloud UI | Consistency with approved corporate identity |

## 6. Business decisions still required

1. Which Jira board ID is authoritative for sprint priority? An issue can exist
   in past/future sprints and several boards: the configured board is the source
   of truth, not the raw Sprint custom field.
2. Is cloud hosting allowed for full supplier XML and employee correspondence?
   Decide access policy, audit, EU data storage/retention and model provider.
3. Can the BA assistant use an approved model API in the cloud, rather than
   relying on the current local Work/Codex automation?
4. Is the source-of-truth brand guide available? Public blue/charcoal palette
   may be imitated, but official brand compliance needs an approved kit.

For Jira Software Cloud sprint REST reference see:
https://developer.atlassian.com/cloud/jira/software/rest/api-group-board/

## 7. Private one-analyst cloud pilot (v2.6 code)

```mermaid
flowchart TD
  Browser["Authorized analyst browser"] --> Caddy["Caddy HTTPS"]
  Caddy --> Nginx["Nginx auth_request"]
  Nginx --> OIDC["oauth2-proxy OIDC / company SSO"]
  Nginx --> APP["Python API: verified email + proxy secret"]
  APP --> DB[("Persistent pilot SQLite volume")]
  Schedule["08:00 Warsaw cloud_scheduler.py"] --> Runner["run_daily.py"]
  Runner --> Jira["Read-only Jira for one explicit assignee"]
  Runner --> LLM["Approved HTTPS LLM model_analysis.py"]
  Runner --> QA["Schema / source fingerprint / priority factors"]
  QA --> DB
  classDef secure fill:#e8edf5,stroke:#58789e,color:#233f62
  class Browser,Caddy,Nginx,OIDC,APP secure
```

Code exists in the PR branch; this topology is **not deployed**
on a corporate cloud. SQLite is a single-user pilot only.
Managed PostgreSQL, HA, approved object storage, backup/restore and
company OIDC credentials remain external prerequisites.
