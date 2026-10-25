"""Deterministic BA claim provenance, rule/QA traceability and concise draft checks.

Important: a matched excerpt proves text occurs in the retrieved Jira record,
NOT that the text's claim is true or an expected transformation is approved.
No network access, no Jira mutations, no raw source text in output diagnostics.
"""
import re
from urllib.parse import urlsplit, urlunsplit
from ba_output_checks import dossier_checks, email_checks, technical_literals

MAX_FINDINGS = 100
REQUIRED_KINDS = ("POSITIVE", "NEGATIVE")
ALLOWED_KINDS = {"POSITIVE", "NEGATIVE", "EDGE"}
TECHNICAL = re.compile(r"\b[A-Za-z][A-Za-z0-9]*Code\b|\b(?:TypeCode|StatusCode|DeliveryStatusCode|SegmentRefID)\b")
FILLER = re.compile(r"\b(?:please kindly|in order to be able to|ensure that everything|as per requirement)\b", re.I)


def compact(text):
    return " ".join(str(text or "").split())


def source_text(obj, budget=160000):
    """Flatten only bounded Jira ADF/comment text, not every metadata field."""
    result = []
    def walk(value, depth=0):
        if depth > 12 or sum(len(x) for x in result) >= budget:
            return
        if isinstance(value, str):
            result.append(value[:50000])
        elif isinstance(value, dict):
            if value.get("type") == "text" and isinstance(value.get("text"), str):
                result.append(value["text"][:50000])
            if "content" in value and isinstance(value["content"], list):
                for child in value["content"][:500]:
                    walk(child, depth + 1)
            elif "body" in value:
                walk(value["body"], depth + 1)
        elif isinstance(value, list):
            for child in value[:500]:
                walk(child, depth + 1)
    walk(obj)
    return compact(" ".join(result))[:budget]


def normalized_url(raw):
    if not isinstance(raw, str) or len(raw) > 2000:
        return None
    try:
        parsed = urlsplit(raw.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return None
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))
    except ValueError:
        return None


def source_registry(issue, related=None):
    """Only actually retrieved issue/linked Jira contents are considered read."""
    registry = {}
    for record in [issue] + list((related or {}).values())[:35]:
        if not isinstance(record, dict):
            continue
        uri = normalized_url(record.get("url"))
        if not uri:
            continue
        text = " ".join([
            str(record.get("summary") or ""),
            source_text(record.get("description") or ""),
            source_text(record.get("descriptionAdf") or ""),
            source_text(record.get("comments") or []),
        ])
        registry[uri] = compact(text)[:160000]
    return registry


def claim_audit(briefing, sources):
    claims = []
    failures = []
    for field, prefix in (("confirmedFacts", "F"), ("rules", "R")):
        for i, record in enumerate((briefing.get(field) or [])[:30], 1):
            if not isinstance(record, dict) or (
                    field == "rules" and record.get("certainty") != "CONFIRMED"):
                continue
            item_id = prefix + str(i)
            url = normalized_url(record.get("sourceUrl"))
            excerpt = compact(record.get("sourceExcerpt") or "")
            if not url or url not in sources:
                state = "SOURCE_NOT_READ"
                failures.append({"code": "CLAIM_SOURCE_NOT_READ", "ref": item_id,
                                 "messageUk": "Наведене джерело не входить до прочитаних Jira/linked records."})
            elif len(excerpt) < 8:
                state = "LINK_ONLY"
                failures.append({"code": "CLAIM_EXCERPT_MISSING", "ref": item_id,
                                 "messageUk": "Посилання на Jira не доводить твердження без цитованого фрагмента."})
            elif excerpt not in sources[url]:
                state = "EXCERPT_NOT_FOUND"
                failures.append({"code": "CLAIM_EXCERPT_NOT_FOUND", "ref": item_id,
                                 "messageUk": "Зазначений текст не знайдено у прочитаному Jira джерелі."})
            else:
                state = "TEXT_PRESENT_NOT_FACT_PROVEN"
            claims.append({"ref": item_id, "sourceState": state,
                           "meaning": "Source excerpt occurrence, NOT truth of claim."})
    return claims, failures


def rule_coverage(briefing):
    rules = (briefing.get("rules") or [])[:30]
    verification = (briefing.get("verification") or [])[:60]
    all_ids = set()
    confirmed = {}
    findings = []
    for i, item in enumerate(rules, 1):
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or "")
        if not identifier or not re.fullmatch(r"R[0-9]{1,3}", identifier):
            findings.append({"code": "RULE_ID_MISSING", "ref": "R" + str(i),
                             "messageUk": "Додай однозначний id правила (R1, R2, ...)."})
            continue
        if identifier in all_ids:
            findings.append({"code": "RULE_ID_DUPLICATED", "ref": identifier,
                             "messageUk": "Один і той самий rule ID використано кілька разів."})
            continue
        all_ids.add(identifier)
        if item.get("certainty") == "CONFIRMED":
            confirmed[identifier] = item
    coverage = {key: set() for key in confirmed}
    for i, item in enumerate(verification, 1):
        if not isinstance(item, dict):
            continue
        refs = item.get("ruleIds") or []
        kind = item.get("kind")
        if not refs or kind not in ALLOWED_KINDS:
            findings.append({"code": "QA_TRACE_MISSING", "ref": "QA" + str(i),
                             "messageUk": "QA-сценарій потребує ruleIds та kind POSITIVE/NEGATIVE/EDGE."})
            continue
        for identifier in refs:
            if identifier not in all_ids:
                findings.append({"code": "QA_UNKNOWN_RULE_ID", "ref": "QA" + str(i),
                                 "messageUk": "QA посилається на невідомий rule ID."})
            elif identifier in confirmed:
                coverage[identifier].add(kind)
    report = []
    for identifier, rule in confirmed.items():
        required = set(REQUIRED_KINDS)
        when = str(rule.get("whenUk") or "")
        if re.search(r"\b(?:AND|OR)\b|(?:\bі\b|\bабо\b)", when, re.I):
            required.add("EDGE")
        missing = sorted(required - coverage[identifier])
        report.append({"ruleId": identifier, "covered": sorted(coverage[identifier]),
                       "missing": missing})
        if missing:
            findings.append({"code": "RULE_QA_GAP", "ref": identifier,
                             "messageUk": "Для правила бракує QA: " + ", ".join(missing)})
    return report, findings


def description_review(description, briefing):
    desc = str(description or "")
    findings = []
    if not desc.strip():
        findings.append({"code": "DESCRIPTION_NOT_PREPARED", "ref": "description",
                         "messageUk": "Готовий опис відсутній; причина має бути в BA-брифінгу."})
        return findings
    if not re.search(r"(?im)^####\s+(?:To Do|Objective|QA)\s*$", desc):
        findings.append({"code": "DESCRIPTION_STRUCTURE_MISSING", "ref": "description",
                         "messageUk": "Не знайдено структурованого розділу Objective, To Do або QA."})
    if not re.search(r"(?im)^####\s+QA\s*$", desc) or not re.search(r"(?im)^\s*(?:[-*]\s*)?Check\b", desc):
        findings.append({"code": "DESCRIPTION_QA_MISSING", "ref": "description",
                         "messageUk": "Відсутні конкретні acceptance checks, що починаються з Check."})
    if re.search(r"(?im)^\s*[-*]?\s*Check\s+(?:that\s+)?(?:everything\s+works|the\s+system\s+works|it\s+works)\s*\.?\s*$", desc):
        findings.append({"code": "DESCRIPTION_QA_GENERIC", "ref": "description",
                         "messageUk": "QA містить загальну перевірку без конкретного очікуваного результату."})
    if FILLER.search(desc):
        findings.append({"code": "DESCRIPTION_FILLER", "ref": "description",
                         "messageUk": "Прибери канцелярські фрази без технічного змісту."})
    sections = []
    for line in desc.splitlines():
        line = compact(re.sub(r"^\s*(?:[-*]\s*)?", "", line))
        if len(line) >= 25 and not line.startswith("#"):
            sections.append(line.casefold())
    if len(sections) != len(set(sections)):
        findings.append({"code": "DESCRIPTION_REPEATS", "ref": "description",
                         "messageUk": "Є дослівне повторення змісту в описі."})
    # Technical field spelling must survive in description, without treating
    # approximate "same-named" mapping candidates as business requirements.
    for rule in (briefing.get("rules") or [])[:30]:
        if not isinstance(rule, dict) or rule.get("certainty") != "CONFIRMED":
            continue
        when, then = str(rule.get("whenUk") or ""), str(rule.get("thenUk") or "")
        tokens = set(TECHNICAL.findall(when + " " + then))
        for field in sorted(tokens):
            if not re.search(r"(?<![A-Za-z0-9_])" + re.escape(field) + r"(?![A-Za-z0-9_])", desc):
                findings.append({"code": "CONFIRMED_FIELD_OMITTED", "ref": field[:80],
                                 "messageUk": "Точне ім'я поля підтвердженої умови або результату відсутнє в Jira описі."})
        for literal in sorted(technical_literals(when, then)):
            if not re.search(r"(?<![A-Za-z0-9_])" + re.escape(literal) + r"(?![A-Za-z0-9_])", desc):
                findings.append({"code": "CONFIRMED_LITERAL_OMITTED", "ref": rule.get("id") or "rule",
                                 "messageUk": "У Jira описі відсутнє точне значення enum/code із підтвердженого правила."})
        for operator in ("AND", "OR"):
            if re.search(r"\b" + operator + r"\b", when, re.I) and not re.search(
                    r"\b" + operator + r"\b", desc, re.I):
                findings.append({"code": "COMPOUND_OPERATOR_OMITTED", "ref": rule.get("id") or "rule",
                                 "messageUk": "Можливо втрачено AND/OR у складеній підтвердженій умові; перевір логіку."})
    return findings


def quality_gate(analysis, issue, related=None, *, attachment_ready=None, supplier_method=None):
    """Inspect model output locally. Never claim semantic validation."""
    briefing = analysis.get("briefing") or {}
    sources = source_registry(issue, related)
    claims, source_findings = claim_audit(briefing, sources)
    coverage, qa_findings = rule_coverage(briefing)
    writing_findings = description_review(analysis.get("standardDescription"), briefing)
    output_findings = dossier_checks(analysis) + email_checks(
        analysis.get("emailDraft"), attachment_ready=attachment_ready,
        verified_supplier_method=supplier_method)
    findings = (source_findings + qa_findings + writing_findings + output_findings)[:MAX_FINDINGS]
    if not claims:
        findings.append({"code": "NO_CONFIRMED_SOURCE_CLAIMS", "ref": "briefing",
                         "messageUk": "Немає підтверджених фактів або правил із перевірюваним джерелом."})
    if not coverage:
        findings.append({"code": "NO_CONFIRMED_RULE_TRACE", "ref": "briefing",
                         "messageUk": "Не сформовано зв'язок підтверджених правил із QA-сценаріями."})
    findings = findings[:MAX_FINDINGS]
    critical = {"CLAIM_SOURCE_NOT_READ", "CLAIM_EXCERPT_NOT_FOUND",
                "CLAIM_EXCERPT_MISSING", "RULE_QA_GAP", "QA_UNKNOWN_RULE_ID",
                "RULE_ID_DUPLICATED", "CONFIRMED_FIELD_OMITTED",
                "CONFIRMED_LITERAL_OMITTED", "COMPOUND_OPERATOR_OMITTED",
                "EMAIL_UNVERIFIED_ATTACHMENT_CLAIM", "EMAIL_METHOD_CONFLICT",
                "OPEN_REQUIREMENTS_PENDING", "OPEN_RULES_PENDING"}
    state = ("BLOCKED" if any(x["code"] in critical for x in findings)
             else "NEEDS_REVIEW" if findings else "STRUCTURALLY_VERIFIED")
    return {
        "version": 2, "state": state,
        "isReadyForReview": state == "STRUCTURALLY_VERIFIED",
        "claims": claims[:60], "qaCoverage": coverage[:30],
        "findings": findings,
        "summary": {"claimsChecked": len(claims),
                    "sourceExcerptsPresent": sum(x["sourceState"] == "TEXT_PRESENT_NOT_FACT_PROVEN"
                                                 for x in claims),
                    "rulesTracked": len(coverage),
                    "rulesFullyCovered": sum(not x["missing"] for x in coverage),
                    "outputFindings": len(output_findings)},
        "limitation": "Excerpt presence and QA links verified mechanically; no semantic proof of correctness.",
    }
