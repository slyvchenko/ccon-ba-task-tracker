# PR #40: source provenance and REST↔supplier pairing safety

**Status:** synthetic CI-tested engineering safeguards, **not** a claim of verified airline integration or completed live BA UAT.

## Exact comparison protocol

| Direction | Required input | Candidate pairing | Blocking ambiguity |
|---|---|---|---|
| REST request → supplier request | Original authorized local ZIP (REST RQ + selected supplier RQ) | Exactly one compatible supplier exchange by shared correlation ID; a unique pair is allowed **only if neither side contains an explicit ID** | Conflicting IDs, missing peer, duplicate supplier calls, repeated REST references or lack of unique correlation |
| Supplier response → REST response | Original authorized local ZIP (selected supplier RS + REST RS) | Same reverse uniqueness requirement, never file sequence/filename proximity | Duplicated response, one-to-many correlation, missing REST RS, multiple retries |
| Jira ↔ Confluence/attachment | Current Jira fingerprint, hash-verified local source, readable exact-quote excerpt | Text occurrence is at most `TEXT_PRESENT_NOT_FACT_PROVEN` | Source missing, hash changed, unread PDF, expired Jira fingerprint, unsupported document or different rule version |
| Kibana error sample | Authorized user browser and exact Jira scope | Read-only list of candidate flows + manual download | No auth, missing flow, unrepresentative sample or only title/URL visible |

### Concrete change to value-level review

- `value_mapping.py` previously allowed **a single REST/supplier pair even with contradictory explicit correlation IDs**. It also allowed **two REST exchanges to reuse the same supplier exchange**. Both cases could look like a credible field mapping. In #40 they are rejected as `CORRELATION_MISMATCH` or `AMBIGUOUS_PAIRING`.
- The result adds `valueReview.coverage[]` by direction: `restExchanges`, `supplierExchanges`, `candidatePairs`, `unpairedRest`, `unpairedSupplier`, plus a bounded `state`. No raw values or correlation IDs are returned. Ambiguity produces **OPEN evidence gaps**, not an invented confirmed transformation or responsible supplier.
- An unmatched REST/supplier pair produces `INCOMPLETE_EXCHANGE` or `UNCORRELATED_EXCHANGE`. `UNIQUE_SINGLE_EXCHANGE` retains its previous label only when **both sides lack explicit correlation IDs**. All successful comparisons remain `CANDIDATE_ONLY`; a matching scalar never proves an application-level rule.

### Prevent stale analysis after a document download

`model_analysis.linked_document_version` now hashes **only the privacy-bounded verification metadata** for attached Jira files and Confluence pages. When a page becomes verified, becomes unread, changes hash or verification status, the existing cached BA analysis is invalidated for regeneration. Previously a newly verified Confluence document could be ignored if Jira fingerprint and supplier ZIP hadn't changed. No page text or attachment contents are written to the fingerprint.

### How to confirm in real BA UAT (not performed by CI)

1. Choose one private NDC issue with matched REST RQ/RS and supplier RQ/RS in the **same cconFlowId**. Verify original ZIP hash, correct supplier and actual request/response chronology against a trusted contract.
2. Find or synthesize a repeated supplier call, retry, cross-flow ID mismatch and partial supplier response. Expect `AMBIGUOUS_PAIRING`, `CORRELATION_MISMATCH`, `INCOMPLETE_EXCHANGE` or `UNCORRELATED_EXCHANGE`, never a validated mapping.
3. Open authorized Confluence and downloaded Jira documents in a local private browser. Change the underlying verified revision and confirm cached analysis re-runs, with no raw document text in model payload or public GitHub.
4. For an actual mapping, independently check `TypeCode`, `FareComponent`, `SegmentRefID`, `StatusCode`, `DeliveryStatusCode`, journey grouping and REST/supplier direction against API documentation. Require negative/edge cases, not just equal scalars.
5. Validate all output assertions against source IDs and screenshots **privately**. The GitHub suite uses synthetic data and does not log into Jira, Kibana, CCON or any supplier.

**Remaining:** EVD-06 live browser auth and EVD-13/BA-09/OUT-04 semantic source agreement are HUMAN UAT gates, not automatically DONE. #41 will address recipient/email/Jira handoff correctness and attachment statements.
