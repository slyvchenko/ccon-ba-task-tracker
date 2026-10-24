# CCON BA Desk: independent quality evaluation

**Purpose:** measure whether the new BA deep review actually improves accuracy,
task readiness and human comprehension on the *same* 20–30 real Jira cases.
This is a local read-only workflow. Do not publish `data/evaluation/` on GitHub.

## Ground rules

- AI self-grading is not accepted as an accuracy benchmark.
- A green CI badge verifies code paths, not whether an NDC mapping is correct.
- Prior and updated analyses must use **the same frozen Jira context fingerprint**.
- A human reviewer must check source comments, actual payloads and unresolved gaps.
- No notes, tickets, status changes, emails or supplier actions may be written externally.
- No confidence percentage based merely on wording or schema completeness.
- A selected but unread ZIP/PDF or inaccessible email is missing evidence, not a verified fact.

## 1. Freeze a diverse cohort of actual issues

After the existing read-only Jira sync has completed on the authorized workstation:

```powershell
py jira_sync.py
py evaluation.py prepare --count 30
```

The command selects 30 distinct issue keys across available topic/complexity buckets
(deterministic, **not a statistically representative random sample**).
If fewer than 30 tasks are available, choose 20–29 explicitly:

```powershell
py evaluation.py prepare --count 20
```

A minimum of 20 is enforced. The tool never fills missing slots with invented cases.
It creates:

- `data/evaluation/selected_cases.json`: frozen issue descriptions, comments,
  issue links, and source fingerprint for comparative review.
- `data/evaluation/reviews.json`: unfilled human review sheet, with 7 criteria,
  critical false claims and minutes needed to reach a useful decision.

The tool intentionally refuses to overwrite existing cohorts or reviews.

## 2. Freeze baseline (old BA analysis)

Do this before updating the scheduled Work/Codex prompt to the v2.4 instructions:

```powershell
py evaluation.py attach --variant baseline --analysis-file inbox/CCON_BA_Snapshot.json
```

It refuses missing analyses and fingerprint mismatches. If the old snapshot
was generated with a different Jira context or without analyses, rerun the
**old** analysis against this frozen cohort first and store the output in
a local file in the same analyses-map / snapshot-tasks format.

Do not use a newer issue payload to improve the old baseline.

## 3. Produce candidate with new BA Deep Review

Update the installed application and the **existing** automation prompt using
`DAILY_AUTOMATION_PROMPT.md` and `BA_DEEP_REVIEW.md`. Do not create an
additional schedule.

For valid A/B evaluation, ask the Work/Codex agent in a single read-only session:

> Using the frozen real Jira cohort in data/evaluation/selected_cases.json,
> apply BA_ANALYSIS_RULES.md, BA_DEEP_REVIEW.md and TASK_DESCRIPTION_RULES.md.
> For each selected case, generate complete analysis including briefing.
> Read no newer Jira updates than the frozen case; use only sources actually
> present/readable at cohort freeze and label any unavailable evidence.
> Write only a local file data/evaluation/candidate_analysis.json with
> {"analyses":{"CCON-123":{...}}}; each item must retain the cohort fingerprint.
> Do not modify Jira, Confluence, email, manual statuses or the production snapshot.

Then freeze the output:

```powershell
py evaluation.py attach --variant candidate --analysis-file data/evaluation/candidate_analysis.json
```

If linked descriptions or actual attachment contents were not frozen/read at
baseline, both versions must be judged with that same limitation. Do not
reinterpret a changed source as a model quality improvement.

## 4. Human reference review (blinded where practical)

Open the frozen source and both frozen prediction sets. For every issue,
first write a short expert ground truth outside the model response:
actual behavior, intended behavior, last *confirmed* decision, open blockers,
testable outputs and evidence URLs. Have a second reviewer audit the
high-risk cases when possible.

In `reviews.json` fill, for **both baseline and candidate**:
- `reviewer` name/identifier
- `reviewed` = true
- Seven `scores` values 0..4:
  - `context_accuracy`: accurate summary of issue and current state
  - `evidence_support`: every important claim supported by read source
  - `decision_history`: correct order and status of decisions
  - `scope_and_requirements`: correct provider/method, no invented mapping or logic
  - `question_usefulness`: actual critical unresolved issues, not noise
  - `qa_correctness`: verifiable QA for confirmed requirement only
  - `next_action_clarity`: precise next action and owner
- `criticalFalseClaims`: exact examples of dangerous false factual statements
- `minutesSpent`: time needed to reach a reliable decision/understanding;
  measure with the same procedure, not estimated wall-clock time of AI execution.

Score meaning:
0 = incorrect or absent; 1 = materially deficient; 2 = partly useful;
3 = good and substantively correct; 4 = verified complete for the available evidence.
If a source is unavailable, grade limitation disclosure, not imagined certainty.

## 5. Evaluate and compare

```powershell
py evaluation.py score
```

Reads local human labels and generates:
- `data/evaluation/results.json`
- `data/evaluation/results.md`

Until all selected cases have human review, result is `INCOMPLETE`.
The tool reports dimension mean and proportion scoring at least 3,
critical false claims and median per-case time saved. It cannot manufacture
baseline quality or infer semantic truth from JSON.

**Acceptance targets**, not reported achievements:

| Dimension | Target |
| --- | --- |
| Human rating at least 3 in every criterion | >= 90% cases |
| Critical false assertions in candidate | 0 |
| Median time saved to reliable understanding | >= 40% |
| Evaluated real-case count | 20–30, 100% independently reviewed |
| Manual Jira/email/Confluence mutations | 0 |

A serious incorrect IF/THEN mapping, a fabricated supplier response or a
missing critical qualification must be corrected and retested, even if the
overall average looks good.

## 6. Ongoing regression

After the baseline is verified, preserve it as an **approved local reference**
for periodic spot checks. Each significant model/prompt version should be
compared on the same frozen examples plus a small newly sampled cohort.
Keep sensitive fixtures local, never in public CI.

The dashboard's structural warnings are useful triage signals only.
They are not human-reviewed evidence that the analysis is correct.

## Operational release gate

- [ ] Existing PR #2 merged/rebased
- [ ] v2.4 PR passes CI and receives code review
- [ ] Application updated on Windows and existing daily prompt replaced
- [ ] Complete same-context baseline/candidate predictions frozen
- [ ] At least 20 genuine cases independently reviewed
- [ ] Quality targets met or failure cases documented
- [ ] Read-only smoke test after deployment; manual notes remain unchanged
