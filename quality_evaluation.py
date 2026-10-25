"""Deterministic preflight diagnostics on a *frozen* 20–30 case A/B cohort.

Never self-grade factual correctness. No network, model, source payload exports
or writes to Jira. Report only aggregate counts by signal/finding, no raw data.
"""
from collections import Counter
from ba_quality_gate import quality_gate
from ba_compactness import profile


def _source(case):
    source = case.get("source") or {}
    issue = {"url": source.get("url"), "summary": case.get("summary", ""),
             "description": source.get("description", ""),
             "descriptionAdf": source.get("descriptionAdf"),
             "comments": source.get("comments") or []}
    related = {}
    for linked in (source.get("linkedContexts") or [])[:35]:
        if isinstance(linked, dict) and isinstance(linked.get("url"), str):
            related[linked.get("key", "")] = linked
    return issue, related


def diagnostics(pack, predictions):
    """Exact frozen-case identity enforced before any score is calculated."""
    cases = pack.get("cases")
    model = predictions.get("analyses")
    if not isinstance(cases, list) or not isinstance(model, dict) or not 20 <= len(cases) <= 30:
        raise ValueError("Frozen 20-30 case pack and analyses map required.")
    keys = [case.get("key") for case in cases]
    if len(set(keys)) != len(keys) or set(keys) != set(model):
        raise ValueError("Prediction scope must match all frozen cases exactly.")
    warning_codes = Counter()
    gate_status = Counter()
    signals = Counter()
    missing_rules = 0
    verified_excerpts = 0
    claimed_excerpts = 0
    words = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Invalid frozen case.")
        analysis = model[case["key"]]
        if not isinstance(analysis, dict) or analysis.get("contextFingerprint") != case.get("contextFingerprint"):
            raise ValueError("Prediction fingerprint mismatch with frozen case.")
        current, related = _source(case)
        # No attachment or linked wiki can be considered read just because it
        # is referenced by the selected case. Only frozen Jira text is used.
        gate = quality_gate(analysis, current, related)
        gate_status[gate["state"]] += 1
        signals[str(analysis.get("signal") or "MISSING")] += 1
        warning_codes.update({x["code"] for x in gate["findings"]})
        missing_rules += sum(bool(x["missing"]) for x in gate["qaCoverage"])
        verified_excerpts += gate["summary"]["sourceExcerptsPresent"]
        claimed_excerpts += gate["summary"]["claimsChecked"]
        words.append(profile(analysis.get("standardDescription"))["words"])
    return {
        "caseCount": len(cases),
        "gateStates": dict(sorted(gate_status.items())),
        "signalCounts": dict(sorted(signals.items())),
        "warningCaseCounts": dict(sorted(warning_codes.items())),
        "rulesMissingQaCaseLinks": missing_rules,
        "excerptsWithFrozenJiraText": verified_excerpts,
        "claimedSourceExcerpts": claimed_excerpts,
        "descriptionWordsAverage": round(sum(words) / len(words), 1),
        "limitations": [
            "Automated preflight only; exact quote is not factual truth.",
            "Offline Jira-only context. Private PDF, wiki and ZIP were not independently read.",
            "A better warning count is not evidence of a better BA result.",
        ],
    }


def compare(pack, baseline, candidate):
    before = diagnostics(pack, baseline)
    after = diagnostics(pack, candidate)
    all_codes = set(before["warningCaseCounts"]) | set(after["warningCaseCounts"])
    return {"status": "PREFLIGHT_ONLY_REQUIRES_HUMAN_REVIEW",
            "baseline": before, "candidate": after,
            "warningDeltaCases": {code: after["warningCaseCounts"].get(code, 0) -
                                  before["warningCaseCounts"].get(code, 0)
                                  for code in sorted(all_codes)},
            "acceptance": "NOT_DETERMINABLE_FROM_DETERMINISTIC_CHECKS"}
