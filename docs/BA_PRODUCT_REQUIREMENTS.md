# CCON BA Desk v2.5: Product requirements, scope and release status

**Owner:** BA workflow. **Updated:** 2026-10-24.
**Policy:** analyze and prepare, never auto-mutate Jira/Confluence or send mail.
The human analyst is responsible for deciding whether to use generated outputs.

## User stories and acceptance criteria

| ID | Priority | User story / requirement | Testable acceptance | Status |
| --- | --- | --- | --- | --- |
| US-01 | P0 | BA can securely access dashboard from any authorized device | Private HTTPS URL, SSO/MFA, no anonymous Jira/ZIP access, persistent state, server independent of user's laptop | TARGET ONLY: cloud architecture drafted; needs approved infra + migration |
| US-02 | P0 | Tasks in currently active sprint always rank above backlog | Sprint membership verified from one configured Jira Software board; all unfinished in-sprint above any outside score | IMPLEMENTED in this PR; integration requires `CCON_JIRA_BOARD_ID` |
| US-03 | P0 | BA can see new, changed and finished tasks and added/removed questions | Daily source-verified delta report; missing from JQL is distinguished from verified Jira Done | IMPLEMENTED in PR #2 + this PR; needs live Jira smoke test |
| US-04 | P0 | Outside-sprint tasks use agreed 0–100 scale | Finite 0–100 scores validated; backlog never outranks active-sprint lane; manual Done remains finished | IMPLEMENTED, CI covered |
| US-05 | P0 | Every PR executes regression checks | GitHub Actions Python/Node, release, and HTTP tests run as a PR status check | IMPLEMENTED in PR #2; recommended to require status check in branch protection |
| US-06 | P1 | Prompts improve daily without silently damaging analysis | After each successful daily analysis, a safe date-versioned adaptive checklist is regenerated from known diagnostics; baseline prompt amendments require human review and A/B scoring | SAFE ADAPTIVE CHECKLIST IMPLEMENTED; autonomous rewrite of core prompt explicitly disallowed |
| US-07 | P1 | BA understands full system flow, features and modules | Current data flow + task sequence + future cloud Mermaid diagrams and module ownership table in repo | DOCUMENTED in `docs/BA_SYSTEM_FLOW.md` |
| US-08 | P1 | Dashboard resembles AERTiCKET corporate visual identity | Text wordmark, blue/charcoal/light canvas tokens, sprint-first navigation; official logo/colors need brand sign-off | INITIAL DESIGN IMPLEMENTED; exact official compliance NOT VERIFIED |
| US-09 | P0 | BA gets rich, reliable task preparation, not a generic summary | 30-second brief, current/target, confirmed facts, source audit, dated decisions, conditions, QA, draft and open questions | IMPLEMENTED in PR #3; real-case accuracy not yet measured |
| US-10 | P1 | Analyze 20–30 real cases independently before quality claims | Identical frozen inputs, separate baseline/candidate, human rubric, zero critical false claims target | LOCAL EVALUATION TOOL IMPLEMENTED in PR #3; actual corporate review not yet performed |

## Source of sprint truth and priority

- Jira board configured by `CCON_JIRA_BOARD_ID`; uses read-only
  Jira Software endpoints to get active sprints and every issue key.
- A missing configuration means `NOT_CONFIGURED`. The UI explicitly
  labels unverified sprint membership; it must never silently assume it.
- A configured board whose pagination cannot be fully verified aborts
  sync before replacing the previous snapshot.
- Priority ordering:
  1. All not-yet-manually-completed tasks confirmed in the active sprint.
  2. Other in-scope not-yet-manually-completed Jira tasks (0–100).
  3. Manually/analytically completed tasks.
  4. Archived tasks no longer in JQL.
- Within each lane, actionable first, waiting second, descending BA score,
  blocked impact and stable previous ordering at ties. Score does not
  override membership; WAIT stays WAIT and manual status wins.
- If more than one active sprint exists on a configured board, each is
  considered in scope, with named membership exposed for review.

## Definition of task changes

- **New:** first analyzed occurrence.
- **Updated:** material analysis, Jira source fingerprint or sprint membership changed.
- **Completed by analysis:** AI signal transitioned to DONE. This does not
  modify Jira status and must not be presented as confirmed Jira Done.
- **Confirmed Jira Done:** a task left in-scope JQL and a fresh read-only
  get-issue request verified `statusCategory=done`.
- **Left scope:** issue no longer in JQL because of reassignment, deletion, visibility, completion uncertainty or other reason; **not**
  counted as Jira Done without verification.
- **New/removed BA questions:** text deltas, with removed never automatically
  labeled "answered".
- **No changes:** source/fingerprint/logic equivalent after normalization.

## Score contract

- User-visible score 0–100; do not invent >100 to force sprint dominance.
- Same bounded scale for sprint and backlog. Sprint dominates at the
  ranking bucket, not at an inflated score.
- Proposed scoring criteria for later empirical calibration:
  business impact (0–25), delivery urgency (0–25), critical dependency
  (0–20), needed BA decision (0–20), confidence/actionability (0–10).
  **This weighting is only proposed, not enforced by the model.**
  Check with actual BA task outcomes before adopting a numeric algorithm.

## Prompt self-improvement safety

- `prompt_calibration.py` consumes only whitelisted quality codes and
  independently reviewed score dimensions. It does not ingest untrusted
  Jira body text into generated instructions.
- After each successful analysis import, it saves
  `data/prompt_calibration/current.md` and a dated JSON trace.
- At the next daily run, Work/Codex reads it as a low-priority checklist.
- Rewriting core BA prompts automatically from unchecked AI-generated
  observations is NOT a quality improvement guarantee and not enabled.
  Baseline changes go through explicit PR + regression + real-case human
  approval, with rollback to previous prompt.

## No-write external boundary

The app **does write local user notes, local drafts, snapshots and review
state** as required. No workflow in scope may POST/PATCH/DELETE to Jira
or Confluence or send an email without a separate, explicitly approved
future user story. Windows mailto is manual draft opening only.

## Release gate

- [ ] PR #2 reviewed and merged
- [ ] PR #3 reviewed and merged
- [ ] This PR CI green and human review completed
- [ ] Authoritative Jira board ID configured
- [ ] Real Jira smoke test with mixed in-sprint/out-of-sprint + Done cases
- [ ] Approve corporate brand tokens/asset use
- [ ] Select company hosting, identity, DB and approved LLM provider
- [ ] Cloud deployment and private access validated independently
