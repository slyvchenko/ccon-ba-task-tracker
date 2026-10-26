"""Analyze 1–30 *already downloaded* Kibana/CCON ZIP evidence manifests.

No Kibana API calls or browser credential access. The local Codex agent follows
kibana_evidence.py action plans, downloads real full ZIPs in its authorized
browser, and supplier_logs.py ingest/layered_evidence.py produces manifests.
This module groups distinct flows by error + supplier method + observed stage
and proposes explicitly UNCONFIRMED root-cause hypotheses.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from app_config import ROOT, utc_now
from storage import read_json, write_json
from supplier_logs import supplier_hint, XML_NAME

MAX_CASES = 30
MAX_SOURCE_FILES = 200
MAX_REPORT_SIZE = 4 * 1024 * 1024
CODE = re.compile(r"^[A-Za-z0-9_.:-]{2,90}$")
KEY = re.compile(r"^CCON-\d+$")


def _method(samples):
    found = set()
    for sample in samples:
        if not isinstance(sample, dict) or sample.get("layer") != "supplier":
            continue
        name = PurePosixPath(str(sample.get("file") or "")).name
        match = XML_NAME.fullmatch(name)
        if match:
            found.add(match["method"])
    return sorted(found)[:20]


def _observations(manifest):
    """Read only structural metadata from the selected issue's own manifest."""
    samples = [s for s in (manifest.get("samples") or [])[:40] if isinstance(s, dict)]
    counts = manifest.get("counts") or {}
    stages = Counter(s.get("layer") for s in samples
                     if s.get("errors") and s.get("layer") in ("rest", "supplier", "errors"))
    codes = sorted({str(item["code"]) for item in (manifest.get("errorCodes") or [])[:100]
                    if isinstance(item, dict) and CODE.fullmatch(str(item.get("code") or ""))})
    # A code's appearance in a payload doesn't establish which component
    # originated it. These are *observed in* stages, never blame.
    observed = {}
    for code in codes:
        observed[code] = sorted({s["layer"] for s in samples
                                if code in (s.get("errors") or [])
                                and s.get("layer") in ("rest", "supplier", "errors")})
    comparisons = (manifest.get("valueReview") or {}).get("comparisons") or []
    changes = sum(len(c.get("sameNamedDifferentValues") or []) for c in comparisons[:30]
                  if isinstance(c, dict))
    candidate_pairs = sum(1 for c in comparisons[:30]
                          if isinstance(c, dict) and c.get("mappingStatus") == "CANDIDATE_ONLY")
    return {"codes": codes, "stages": observed, "methods": _method(samples),
            "layerCounts": {name: max(0, int(counts.get(name) or 0))
                            for name in ("rest", "supplier", "errors")},
            "candidatePairCount": candidate_pairs,
            "differentNamedFieldCount": changes,
            "hasAmbiguousMapping": bool(
                {"AMBIGUOUS_PAIRING", "UNCORRELATED_EXCHANGE",
                 "CORRELATION_MISMATCH", "INCOMPLETE_EXCHANGE"} &
                set((manifest.get("valueReview") or {}).get("issues") or []))}


def _make_case(manifest, key, expected_supplier):
    if not isinstance(manifest, dict) or manifest.get("issueKey") != key:
        return None
    if manifest.get("supplier") != expected_supplier:
        return None
    flow = manifest.get("flowId")
    if not isinstance(flow, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", flow
    ):
        return None
    source_hash = manifest.get("sourceSha256")
    if not isinstance(source_hash, str) or not re.fullmatch("[0-9a-f]{64}", source_hash):
        return None
    return {
        "flowId": flow.lower(), "sourceSha256": source_hash,
        "capturedAt": str(manifest.get("createdAt") or "")[:40],
        "supplier": expected_supplier,
        "observations": _observations(manifest),
        "completeness": {
            "rest": bool((manifest.get("counts") or {}).get("rest")),
            "supplier": bool((manifest.get("counts") or {}).get("supplier")),
            "errors": bool((manifest.get("counts") or {}).get("errors")),
        },
    }


def investigate_cases(cases, key, supplier, *, code=None, max_cases=MAX_CASES,
                      discoverable=None):
    """Pure, reproducible report from local bounded, verified per-flow evidence."""
    if not KEY.fullmatch(key) or not isinstance(supplier, str) or not supplier:
        raise ValueError("Invalid issue or supplier.")
    if type(max_cases) is not int or not 1 <= max_cases <= MAX_CASES:
        raise ValueError("At most 30 distinct error cases can be analyzed.")
    if code is not None and not CODE.fullmatch(code):
        raise ValueError("Invalid error code filter.")

    found = {}
    for item in cases:
        if not isinstance(item, dict) or item.get("supplier") != supplier:
            continue
        flow = item.get("flowId")
        if not isinstance(flow, str):
            continue
        # Deduplicate the same cconFlowId across repeated ZIP exports: keep
        # newest (createdAt then source hash). Never inflate error prevalence.
        prior = found.get(flow)
        if prior is None or (item.get("capturedAt", ""), item.get("sourceSha256", "")) > (
            prior.get("capturedAt", ""), prior.get("sourceSha256", "")):
            found[flow] = item
    all_cases = sorted(found.values(), key=lambda x: (x["flowId"], x["sourceSha256"]))
    if code:
        filtered = [x for x in all_cases if code in x["observations"]["codes"]]
    else:
        filtered = all_cases
    selected = filtered[:max_cases]
    groups = {}
    for case in selected:
        observations = case["observations"]
        methods = observations["methods"] or ["UNVERIFIED_METHOD"]
        codes = ([code] if code else observations["codes"]) or ["NO_ERROR_CODE_OBSERVED"]
        for err in codes:
            for method in methods:
                label = (err, method)
                item = groups.setdefault(label, {"errorCode": err, "supplierMethod": method,
                    "caseIds": [], "observedInLayers": Counter(),
                    "mappingDifferenceCases": [], "missingSupplierCases": []})
                item["caseIds"].append(case["flowId"])
                for stage in observations["stages"].get(err, []):
                    item["observedInLayers"][stage] += 1
                if observations["differentNamedFieldCount"]:
                    item["mappingDifferenceCases"].append(case["flowId"])
                if not case["completeness"]["supplier"]:
                    item["missingSupplierCases"].append(case["flowId"])
    results = []
    for group in groups.values():
        results.append({
            "errorCode": group["errorCode"], "supplierMethod": group["supplierMethod"],
            "caseCount": len(set(group["caseIds"])),
            "flowIds": sorted(set(group["caseIds"])),
            "observedInLayers": dict(sorted(group["observedInLayers"].items())),
            "mappingDifferenceFlowIds": sorted(set(group["mappingDifferenceCases"])),
            "missingSupplierFlowIds": sorted(set(group["missingSupplierCases"])),
        })
    results.sort(key=lambda x: (-x["caseCount"], x["errorCode"], x["supplierMethod"]))
    hypotheses = []
    for item in results[:30]:
        support = item["flowIds"][:30]
        code_label = item["errorCode"]
        if item["mappingDifferenceFlowIds"]:
            hypotheses.append({
                "titleUk": "Можлива неправильна трансформація REST ↔ supplier",
                "classification": "HYPOTHESIS_NOT_CONFIRMED",
                "errorCode": code_label,
                "supplierMethod": item["supplierMethod"],
                "supportingFlowIds": item["mappingDifferenceFlowIds"][:30],
                "observationUk": "В окремих спарених обмінах є однойменні поля з різними значеннями.",
                "alternativeUk": "Відмінності можуть бути правильною трансформацією за контрактом.",
                "verificationUk": "Зіставити повні приватні payload та підтверджені mapping rules; перевірити контрприклад без помилки.",
            })
        if item["observedInLayers"].get("supplier"):
            hypotheses.append({
                "titleUk": "Помилка присутня в supplier-відповіді",
                "classification": "HYPOTHESIS_NOT_CONFIRMED",
                "errorCode": code_label,
                "supplierMethod": item["supplierMethod"],
                "supportingFlowIds": support,
                "observationUk": "Код помилки виявлено на supplier-рівні; це не доводить сторону, яка створила першопричину.",
                "alternativeUk": "Запит CCON міг передати некоректні дані; постачальник міг коректно відхилити їх.",
                "verificationUk": "Порівняти supplier RQ/RS, REST RQ/RS, правила контракту та успішний flow.",
            })
        elif item["observedInLayers"].get("errors") or item["observedInLayers"].get("rest"):
            hypotheses.append({
                "titleUk": "Помилка спостерігається на REST/errors рівні",
                "classification": "HYPOTHESIS_NOT_CONFIRMED",
                "errorCode": code_label,
                "supplierMethod": item["supplierMethod"],
                "supportingFlowIds": support,
                "observationUk": "У вибірці немає однозначного підтвердження походження коду із supplier response.",
                "alternativeUk": "Це може бути локальна валідація, перетворення, timeout або пропущений supplier log.",
                "verificationUk": "Перевірити REST→supplier call timeline, retries і supplier responses для всіх affected flows.",
            })
    coverage = {
        "withRest": sum(c["completeness"]["rest"] for c in selected),
        "withSupplier": sum(c["completeness"]["supplier"] for c in selected),
        "withErrorLayer": sum(c["completeness"]["errors"] for c in selected),
        "withCandidatePairs": sum(bool(c["observations"]["candidatePairCount"]) for c in selected),
    }
    gaps = []
    if not selected:
        gaps.append("Немає валідних локально завантажених ZIP/manifests для цієї помилки.")
    if not code:
        gaps.append("Не задано конкретний error code: групи НЕ означають одну й ту саму помилку.")
    if len(filtered) > max_cases:
        gaps.append("Є більше прикладів, ніж ліміт: звіт охоплює лише відібрані flows, не всю Kibana-вибірку.")
    if coverage["withSupplier"] < len(selected):
        gaps.append("Не для кожного flow доступний supplier layer; походження помилки не можна підтвердити.")
    if coverage["withRest"] < len(selected):
        gaps.append("Не для кожного flow доступний REST layer.")
    if coverage["withErrorLayer"] < len(selected):
        gaps.append("Окрема errors папка недоступна в частині flows; це не означає відсутність помилок.")
    if any(c["observations"]["hasAmbiguousMapping"] for c in selected):
        gaps.append("Є неоднозначне спарювання REST ↔ supplier; вимагати correlation/time context.")
    gaps.append("Без успішних контрприкладів і перевірених supplier/API contracts першопричина не підтверджена.")
    return {
        "schemaVersion": 1, "issueKey": key, "supplier": supplier,
        "requestedErrorCode": code, "maxCases": max_cases,
        "availableUniqueFlows": len(filtered), "analyzedCases": len(selected),
        "sampling": "FIRST_N_BY_FLOW_ID_DETERMINISTIC_NOT_STATISTICALLY_REPRESENTATIVE",
        "scope": "LOCAL_DOWNLOADED_MANIFESTS_ONLY",
        "source": "Kibana linked or CCON ZIPs manually downloaded by authorized local Codex",
        "coverage": coverage,
        "cases": selected,
        "groups": results[:90],
        "hypotheses": hypotheses[:70],
        "questionsUk": list(dict.fromkeys(gaps)),
        "causality": "ROOT_CAUSE_UNCONFIRMED",
        "browserAccess": "NOT_PERFORMED_BY_THIS_SCRIPT",
    }


def build_investigation(root=ROOT, issue_key=None, code=None, max_cases=MAX_CASES):
    """Require complete personal scope and save only safe aggregates."""
    if not issue_key or not KEY.fullmatch(issue_key):
        raise ValueError("One valid CCON issue key is required.")
    root = Path(root)
    context = read_json(root / "data/jira_context.json", {})
    issue = (context.get("issues") or {}).get(issue_key) or {}
    if context.get("complete") is not True or not issue:
        raise ValueError("Issue not in complete personal Jira scope.")
    supplier = supplier_hint(issue.get("summary") or "")
    if not supplier:
        raise ValueError("Supplier not verified from the issue summary.")
    folder = root / "data/evidence" / issue_key
    data = []
    if folder.is_dir():
        for file in sorted(folder.glob("*.json"))[:MAX_SOURCE_FILES]:
            if file.is_symlink() or file.stat().st_size > MAX_REPORT_SIZE:
                continue
            try:
                record = read_json(file, {})
                sample = _make_case(record, issue_key, supplier["name"])
            except (OSError, TypeError, ValueError, KeyError):
                continue
            if sample:
                data.append(sample)
    report = investigate_cases(data, issue_key, supplier["name"],
                               code=code, max_cases=max_cases)
    report["generatedAt"] = utc_now()
    report["sourceManifestCount"] = len(data)
    report["dataFingerprint"] = __import__("hashlib").sha256(json.dumps(
        data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    location = root / "data/investigations" / (issue_key + ".json")
    write_json(location, report, 4 * 1024 * 1024)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--error-code", default=None)
    parser.add_argument("--max-cases", type=int, default=MAX_CASES)
    args = parser.parse_args()
    output = build_investigation(args.root, args.issue, args.error_code, args.max_cases)
    print(json.dumps({key: output[key] for key in (
        "issueKey", "supplier", "requestedErrorCode", "analyzedCases",
        "availableUniqueFlows", "coverage", "causality", "questionsUk"
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
