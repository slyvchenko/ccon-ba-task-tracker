# CCON BA Desk vNext: BA review assurance

Status: **proposed product baseline; implementation PR pending validation**  
Updated: 2026-10-24  
Owner: CCON business analysis workflow

## 1. Product goal

Each scheduled BA review should produce an actionable, traceable comparison with the prior analyzed state, rather than regenerating a plausible but unverified summary. Generated recommendations must not silently modify Jira, Confluence, sent mail, manual decisions or saved correspondence.

## 2. Stakeholders and operating assumptions

- Primary user: business analyst reviewing CCON Jira integration tasks.
- Sources: full Jira context collected by the existing read-only sync, previous analysis and local manual notes. Jira may contain inaccessible links and unverified claims.
- The existing Windows installation and Work/Codex automation stay in place. GitHub writes do not update the local installation.
- English is used for Jira task drafts; Ukrainian for BA reasoning/questions and user-facing daily reporting.
- AI may be wrong. A report warning is diagnostic, not a proof of inconsistency. A removed question is not automatically answered.

## 3. Functional requirements and acceptance

| ID | Priority | Requirement | Acceptance criterion |
| --- | --- | --- | --- |
| FR-01 | P0 | Compare current completed analysis against the last locally imported analysis | NEW, UPDATED, COMPLETED, REOPENED, UNCHANGED categories are deterministic; order/whitespace changes in questions do not produce false alerts |
| FR-02 | P0 | Detect missing/open question changes | Added/removed questions are preserved as separate arrays; removed is not labeled answered |
| FR-03 | P0 | Surface meaningful Jira source changes | A changed context fingerprint marks the task UPDATED even if its action text did not change |
| FR-04 | P0 | Flag contradictory recommendations | WAIT without evidence or waitingRequired, WRITE without needsEmail, DONE with open questions, actionable recommendations without evidence and descriptions without QA produce warnings |
| FR-05 | P0 | Preserve user authority | Manual status, notes and edited email drafts remain untouched; the report is read-only |
| FR-06 | P1 | Make reports inspectable | After successful analysis import, a local JSON file and localhost JSON/Markdown endpoints are available; before the first review a clear empty state is returned |
| FR-07 | P1 | Enforce the scoring contract | Only finite numeric queueScore in the inclusive range 0–100 is accepted; invalid analysis cannot replace the existing snapshot |
| FR-08 | P1 | Verify changes before merge | CI runs Python, Node, release and HTTP regression tests on PRs without enterprise credentials |

## 4. Non-functional requirements

- No dependency added to runtime (Python standard library only).
- Localhost access boundaries and no automatic Jira/mail writes are maintained.
- A failed report write after successful snapshot import is exposed separately; it must not masquerade as a failed import.
- Report generation must not need Jira credentials and must compare supplied deterministic state.
- Sensitive Jira content is local runtime data, not part of ZIP release or CI fixtures.
- Preserve backwards compatibility with existing SQLite fields and JSON snapshot consumers.

## 5. Out of scope for this increment

1. Independently verifying whether cited Jira evidence supports a generated technical requirement.
2. Semantic matching of paraphrased open questions across multiple languages.
3. Scheduling/running Work/Codex on a powered-off Windows computer.
4. Writing Jira issues, sending mail, or changing user statuses.
5. Automated evaluation of AI precision and recall on real company tickets.

## 6. Follow-up product decisions

- Should source citation be mandatory for READY/WRITE/DECIDE, blocking import, or advisory only? **Proposed default: advisory until measured false-positive rate.**
- Should a task be considered complete only after a human-set DONE, regardless of AI signal? **Proposed default: yes for workflow status; AI COMPLETED is only report metadata.**
- What is the expected accuracy target for generated requirement drafts? **Needs a labeled 20–30 ticket baseline and domain-expert review.**
- Can enterprise-approved hosted execution access Jira and logs? **Requires security approval; no cloud migration in this change.**

## 7. UAT scenarios

- Re-run unchanged issue and questions with different whitespace/order; the report should remain unchanged.
- Modify Jira payload/comments and keep similar AI action; sourceChanged should still be true.
- Add two questions, remove one; show question deltas but never claim the removed question was answered.
- AI says WAIT without proof, WRITE while needsEmail=false, DONE with open questions; list warnings without dropping unrelated tasks.
- Set manual IN PROGRESS and custom letter; run import; manual values must survive.
- Return a queueScore of 101; reject before changing persisted snapshot.
- Open the report in dashboard; verify no report is visible before the first successful review, and the report is local-only.
- Simulate failed Jira sync; it must not be counted as successful analysis.

## 8. Release checklist

- [ ] CI green on GitHub PR
- [ ] Peer review of code and test coverage
- [ ] Deploy updated files to Windows installation
- [ ] Update the existing scheduled Work/Codex prompt, without changing the schedule
- [ ] Complete one live read-only Jira run and manually evaluate the first report
- [ ] Record baseline agreement/revision feedback
