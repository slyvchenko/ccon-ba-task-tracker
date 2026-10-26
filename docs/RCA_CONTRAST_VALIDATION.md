# #44: RCA contrast without fabricated successful examples

Root-cause analysis needs **negative and boundary cases**, but local downloaded manifests are not the full population of airline requests.

## Safe contrast candidates

Given a requested error code and one in-scope issue/supplier:

- Select up to 30 **distinct affected flows** in deterministic order from already imported, privacy-bounded CCON manifests.
- Separately discover flows for the **same Jira issue and supplier** where the requested error code was **not observed in parsed evidence**. Their count and at most 10 flow IDs become `contrastCandidateCount` and `contrastCandidateFlowIds`.
- Explicit label: `NO_TARGET_ERROR_CODE_OBSERVED_NOT_SUCCESS_PROOF`. This is NOT a verified successful operation, NOT a fixed bug, and NOT proof the supplier did anything correctly. Errors in missing/unread log layers may exist.
- Never include contrast flows in the affected-case denominator, affected grouping, error prevalence, hypothesis support or reported representative sample.
- Deduplicate repeated ZIP manifests for one flow and never use wrong-supplier or wrong-issue manifests.
- If there are no contrast candidates, show a specific gap requesting an authorized reference exchange. If there are candidates, advise manual REST RQ→supplier RQ/RS→REST RS verification, timestamps, actual confirmed API contract and enough opposing successful cases.

## Human UAT boundary

Test with a frozen 20–30-case private corpus of CCON tasks and source ZIPs, obtain independent BA-verified expected behavior including success cases **with confirmed success status** rather than the absence of one error code, and validate source fingerprint. Never paste passenger details, supplier XML or access tokens into public CI or GitHub reviews.

The local script and prompts remain read-only. Root-cause confidence is always `ROOT_CAUSE_UNCONFIRMED` until independent reviewer validation. The existing 30-case deterministic selection **is not statistically representative**.

## Verification

`tests/test_error_series.py` now covers separate affected and contrast groups, 10-ID cap, dedup, missing counterexample warning, and no contrast without a specified target error. Real supplier success, timeout or booking completion remains untested.
