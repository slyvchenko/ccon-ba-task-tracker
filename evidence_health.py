"""Privacy-bounded evidence coverage, error taxonomy and recurrence indicators.

Calculated only from the user's local per-flow ZIP evidence manifests.
An error code is a *classification clue*, not proof that any provider caused
the failure. No raw REST/supplier payload values or ZIP paths are emitted.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from app_config import ROOT, utc_now
from storage import read_json
from supplier_logs import flow_references, supplier_hint
from evidence_trends import event_window, observed_event_days, recurrence_window

UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
CODE = re.compile(r"^[A-Za-z0-9_.:-]{2,90}$")
RULES = [
    ("TIMEOUT_OR_CONNECTIVITY_CANDIDATE", re.compile(r"TIMEOUT|TIMED.?OUT|CONNECTION|NETWORK|SOCKET|HTTP_?(502|503|504)", re.I)),
    ("VALIDATION_OR_INPUT_CANDIDATE", re.compile(r"VALID|MISSING|REQUIRED|INVALID|BAD.?REQUEST|HTTP_?400", re.I)),
    ("MAPPING_OR_CONTRACT_CANDIDATE", re.compile(r"MAP|TRANSFORM|SCHEMA|FARECOMPONENT|SEGMENTREFID|PARSE|MISMATCH", re.I)),
    ("PROVIDER_REJECTION_CANDIDATE", re.compile(r"REJECT|REFUSED|DECLINED|UNSUPPORTED|NOT.?ALLOWED", re.I)),
    ("CCON_PROCESSING_CANDIDATE", re.compile(r"INTERNAL|EXCEPTION|NULL.?POINTER|HTTP_?500", re.I)),
]
MAX_FILES = 200


def classify_error(code):
    """Heuristic error category; never a verified origin or root cause."""
    if not isinstance(code, str) or not CODE.fullmatch(code):
        return "UNCLASSIFIED"
    for name, test in RULES:
        if test.search(code):
            return name
    return "UNCLASSIFIED"


def analyze_health(issue, manifests):
    supplier = supplier_hint(issue.get("summary") or "")
    supplier_name = supplier["name"] if supplier else None
    expected = {x["flowId"] for x in flow_references(issue)}
    cases = {}
    for record in manifests[:MAX_FILES]:
        if not isinstance(record, dict) or record.get("supplier") != supplier_name:
            continue
        flow = record.get("flowId")
        if not isinstance(flow, str) or not UUID.fullmatch(flow.lower()):
            continue
        flow = flow.lower()
        row = {
            "flowId": flow,
            "createdAt": str(record.get("createdAt") or "")[:35],
            "counts": {k: max(0, int((record.get("counts") or {}).get(k) or 0))
                       for k in ("rest", "supplier", "errors")},
            "codes": sorted({str(v["code"]) for v in (record.get("errorCodes") or [])[:100]
                             if isinstance(v, dict) and CODE.fullmatch(str(v.get("code") or ""))}),
            "pairedCandidates": len(((record.get("valueReview") or {}).get("comparisons") or [])[:30]),
            "eventWindow": event_window(record),
            "observedEventDaysUtc": observed_event_days(record),
        }
        # Replacement exported same flow should not inflate frequency.
        prior = cases.get(flow)
        if prior is None or row["createdAt"] > prior["createdAt"]:
            cases[flow] = row

    reference = expected or set(cases)
    reported = []
    for flow in sorted(reference | set(cases)):
        case = cases.get(flow)
        counts = (case or {}).get("counts") or {}
        missing = []
        if case is None:
            missing.append("ZIP_NOT_ANALYZED")
        else:
            if not counts.get("rest"):
                missing.append("REST_MISSING")
            if not counts.get("supplier"):
                missing.append("SELECTED_SUPPLIER_MISSING")
            if not counts.get("errors"):
                missing.append("ERROR_LAYER_MISSING_OR_NOT_EXPORTED")
            if not case["pairedCandidates"]:
                missing.append("NO_VALUE_MAPPING_CANDIDATE")
        reported.append({
            "flowId": flow, "source": "JIRA_FILTER" if flow in expected else "LOCAL_MANIFEST_ONLY",
            "hasRest": bool(counts.get("rest")), "hasSupplier": bool(counts.get("supplier")),
            "hasErrors": bool(counts.get("errors")),
            "hasCandidatePair": bool((case or {}).get("pairedCandidates")),
            "gaps": missing,
        })

    category_groups = defaultdict(lambda: {"flows": set(), "observedStages": defaultdict(int)})
    for case in cases.values():
        for code in case["codes"]:
            label = classify_error(code)
            category_groups[(code, label)]["flows"].add(case["flowId"])
    taxonomy = [{"code": code, "category": category,
                 "caseCount": len(v["flows"]), "flowIds": sorted(v["flows"])[:30],
                 "status": "HEURISTIC_NOT_CONFIRMED_CAUSE"}
                for (code, category), v in category_groups.items()]
    taxonomy.sort(key=lambda x: (-x["caseCount"], x["code"]))
    windows = recurrence_window(list(cases.values()))
    repeated = [{**item, "repeatSignal": "REPEATED_ONLY_IN_DOWNLOADED_FLOWS",
                 "temporalEvidence": windows.get(item["code"])}
                for item in taxonomy if item["caseCount"] > 1][:30]

    count = len(expected) if expected else None
    observed = sum(1 for flow in expected if flow in cases)
    with_both = sum(1 for flow in expected if flow in cases and
                    cases[flow]["counts"]["rest"] and cases[flow]["counts"]["supplier"])
    return {
        "source": "LOCAL_MANIFESTS_ONLY", "supplier": supplier_name,
        "expectedFlowCount": count, "availableEvidenceFlowCount": len(cases),
        "analyzedExpectedFlowCount": observed if count is not None else None,
        "restSupplierCoverage": round(with_both / count, 3) if count else None,
        "expectedFlowSource": "JIRA_CCON_FLOW_FILTERS" if count is not None else "NO_VERIFIED_JIRA_FLOW_FILTERS",
        "flows": reported[:100],
        "taxonomy": taxonomy[:60], "recurrence": repeated,
        "uncertainty": (
            "Codes identify potential classes, not origin or root cause. "
            "No statistically representative prevalence is claimed. "
            "Flow payload event timestamps do not establish error onset. "
            "A missing error folder does not prove absence of errors."
        ),
    }


def health_for_issue(root=ROOT, key=None):
    from ba_questions import task_in_scope
    task_in_scope(root, key)
    root = Path(root)
    context = read_json(root / "data/jira_context.json", {})
    issue = context["issues"][key]
    folder = root / "data/evidence" / key
    records = []
    if folder.is_dir():
        for path in sorted(folder.glob("*.json"))[:MAX_FILES]:
            if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
                continue
            value = read_json(path, {})
            if isinstance(value, dict) and value.get("issueKey") == key:
                records.append(value)
    return analyze_health(issue, records)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--issue", required=True)
    p.add_argument("--root", type=Path, default=ROOT)
    args = p.parse_args()
    print(json.dumps(health_for_issue(args.root, args.issue), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
