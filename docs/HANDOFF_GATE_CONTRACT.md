# v2.41: Manual Jira/email handoff and attachment truth

**Applies only to the local single-BA Desk.** No Jira mutation, supplier send or Outlook delivery automation is added.

## Critical invariant

A sentence asserting that supplier logs **are attached** may appear in a generated supplier email only when the per-task catalog reports **overall `READY`**, meaning every expected `cconFlowId` for the current authorized Jira context has a non-stale, hash-validated selected-supplier ZIP with no review warnings. One valid flow and one missing flow is `PARTIAL`, **not ready**. No flow, unknown supplier, wrong Jira fingerprint, archive integrity failure, unapproved download or `NEEDS_REVIEW` is also not ready.

`normalize_draft(..., attachment_ready=False)` defaults to **no attachment claim**. A deliberate `attachment_ready=True` is required to generate that sentence. The original body/recipient are still editable by a human; unknown readiness or a human-edited claim triggers local QA finding `EMAIL_UNVERIFIED_ATTACHMENT_CLAIM`. No model may turn an unknown `None` into implicit yes.

## Safe handoff protocol

1. Confirm the actual Jira issue remains in the user's own scope and its context fingerprint matches the current analysis.
2. Check that the supplier has been identified from source, not guessed; verify exact method from the selected supplier XML and optional REST error. Keep REST operation vs supplier method distinct.
3. If an email is required, independently verify recipient identity and routing using approved corporate documentation or existing validated thread; **a syntactically valid address is not ownership proof**. Unknown recipients stay empty and the operator must fill them manually.
4. Inspect `/api/logs/{issue}` states. Only an **overall READY** state permits the statement `Logs are attached for your reference.`. If `PARTIAL`, `NEEDS_REVIEW`, `PENDING`, `BLOCKED`, `FAILED`, `STALE`, leave the attachment claim out and describe exactly which flow/ZIP remains missing.
5. Review the plain text Jira technical description for precise `StatusCode`, `DeliveryStatusCode`, `TypeCode`, `SegmentRefID` literals, AND/OR and positive/negative/edge QA results. `STRUCTURALLY_VERIFIED` remains a technical gate, not proof of a business rule.
6. Copy, locally approve, and open in Outlook are different explicit human actions. Neither copying nor opening mail means `SENT`. Uploading ZIP must be confirmed in the actual mail composer by the operator. The system never sends or updates Jira automatically.

## Synthetic regression cases

- A single complete and verified flow permits the statement.
- One current valid ZIP plus another expected missing `cconFlowId` returns `PARTIAL`, so the generated email **cannot** claim logs are attached.
- A standalone call to `normalize_draft` defaults to no claim even when input contains the legacy boilerplate sentence. The explicit verified state is idempotent and produces exactly one sentence.
- `email_checks` blocks an unverified affirmative sentence for both `False` **and** unknown (`None`) attachment readiness; a future/negated claim remains a distinct case.
- No tests use real Jira/PNR/customer content. Corporate gold case approval, real Outlook attachment verification and supplier method correctness still need UAT.

## Remaining gates

`BA-01/02/05`, `OUT-01/02`, `QUICK-02/03/04` retain independent real supplier/Jira UAT. Human-approved description is still local, needs explicit action, and cannot be inferred from green synthetic tests. Next release package #42 focuses on focus/task action cycle, followed by priority/quality/performance hardening.
