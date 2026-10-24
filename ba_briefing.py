"""Structured BA case briefing. It describes provenance, not proof of truth.

This is additive: older snapshots remain valid, and no write-capable Jira API exists.
"""
from urllib.parse import urlparse

READINESS = ("READY_FOR_REVIEW", "NEEDS_CONFIRMATION", "INSUFFICIENT_CONTEXT")
DECISION_STATES = ("CONFIRMED", "PROPOSED", "SUPERSEDED", "DISPUTED")
CERTAINTY = ("CONFIRMED", "OPEN")
SOURCE_STATES = ("READ", "UNAVAILABLE", "REFERENCE_ONLY")


def value_text(value, label, limit, nonempty=False):
    if not isinstance(value, str) or len(value) > limit or (nonempty and not value.strip()):
        raise ValueError(f"{label} must be text with maximum {limit} characters"
                         + (" and may not be empty." if nonempty else "."))


def url(value, label):
    value_text(value, label, 2000)
    if value and urlparse(value).scheme not in ("http", "https"):
        raise ValueError(label + " must be an HTTP(S) URL.")


def text_list(record, field, limit=30):
    values = record.get(field)
    if not isinstance(values, list) or len(values) > limit:
        raise ValueError(f"briefing.{field} must be a list of at most {limit} items.")
    for item in values:
        value_text(item, f"briefing.{field} item", 3000, nonempty=True)


def object_list(record, field, keys, limit=30):
    values = record.get(field)
    if not isinstance(values, list) or len(values) > limit:
        raise ValueError(f"briefing.{field} must be a list of at most {limit} items.")
    for i, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError(f"briefing.{field}[{i}] must be an object.")
        for name in keys:
            value_text(item.get(name), f"briefing.{field}[{i}].{name}", 5000,
                       nonempty=name not in ("sourceUrl", "date"))
        url(item.get("sourceUrl"), f"briefing.{field}[{i}].sourceUrl")


def validate_briefing(briefing):
    """Validate shape and dangerous URLs. It cannot verify semantic accuracy."""
    if not isinstance(briefing, dict):
        raise ValueError("analysis.briefing must be an object.")
    for name in ("overviewUk", "currentUk", "targetUk", "businessImpactUk",
                 "technicalScopeUk", "readinessReasonUk"):
        value_text(briefing.get(name), "briefing." + name, 6000)
    if briefing.get("readiness") not in READINESS:
        raise ValueError("briefing.readiness must be one of " + ", ".join(READINESS))
    for name in ("risksUk", "unknownsUk"):
        text_list(briefing, name)
    object_list(briefing, "confirmedFacts", ("textUk", "sourceUrl"))
    object_list(briefing, "timeline", ("date", "eventUk", "status", "sourceUrl"))
    object_list(briefing, "rules", ("whenUk", "thenUk", "certainty", "sourceUrl"))
    object_list(briefing, "verification", ("scenarioUk", "expectedUk", "sourceUrl"))
    if "sourceAudit" in briefing:
        object_list(briefing, "sourceAudit", ("descriptionUk", "status", "sourceUrl"))
    for i, item in enumerate(briefing["timeline"]):
        if item["status"] not in DECISION_STATES:
            raise ValueError(f"briefing.timeline[{i}].status is invalid.")
    for i, item in enumerate(briefing.get("sourceAudit", [])):
        if item["status"] not in SOURCE_STATES:
            raise ValueError(f"briefing.sourceAudit[{i}].status is invalid.")
    ids = set()
    for i, item in enumerate(briefing.get("confirmedFacts", [])):
        if "sourceExcerpt" in item:
            value_text(item["sourceExcerpt"], f"briefing.confirmedFacts[{i}].sourceExcerpt", 2000)
    for i, item in enumerate(briefing["rules"]):
        if item["certainty"] not in CERTAINTY:
            raise ValueError(f"briefing.rules[{i}].certainty is invalid.")
        if "sourceExcerpt" in item:
            value_text(item["sourceExcerpt"], f"briefing.rules[{i}].sourceExcerpt", 2000)
        if "id" in item:
            import re
            identifier = item["id"]
            if not isinstance(identifier, str) or not re.fullmatch(r"R[0-9]{1,3}", identifier):
                raise ValueError(f"briefing.rules[{i}].id must be R1, R2, ...")
            if identifier in ids:
                raise ValueError("Duplicate rule ID in briefing.rules.")
            ids.add(identifier)
    for i, item in enumerate(briefing["verification"]):
        if "ruleIds" in item:
            refs = item["ruleIds"]
            if (not isinstance(refs, list) or len(refs) > 30 or
                    any(not isinstance(ref, str) or len(ref) > 30 for ref in refs)):
                raise ValueError(f"briefing.verification[{i}].ruleIds must be string IDs.")
        if "kind" in item and item["kind"] not in ("POSITIVE", "NEGATIVE", "EDGE"):
            raise ValueError(f"briefing.verification[{i}].kind is invalid.")


def audit_briefing(analysis, context=None):
    """Non-blocking, conservative warnings, never a hallucination detector."""
    briefing = analysis.get("briefing")
    warnings = []
    def add(code, text):
        warnings.append({"code": code, "messageUk": text})
    if not briefing:
        add("BRIEF_MISSING", "Немає повного структурованого BA-брифінгу.")
        return warnings
    if not briefing.get("overviewUk", "").strip():
        add("OVERVIEW_MISSING", "Немає короткого пояснення ситуації.")
    if not briefing.get("confirmedFacts"):
        add("NO_CONFIRMED_FACTS", "Немає підтверджених фактів із джерелами.")
    elif any(not item.get("sourceUrl") for item in briefing["confirmedFacts"]):
        add("FACT_WITHOUT_SOURCE", "Деякі підтверджені факти не мають джерела.")
    if any(not item.get("sourceUrl") and item.get("certainty") == "CONFIRMED"
           for item in briefing.get("rules", [])):
        add("RULE_WITHOUT_SOURCE", "Підтверджена умова не має посилання на джерело.")
    if briefing["readiness"] == "READY_FOR_REVIEW":
        if not briefing.get("targetUk", "").strip():
            add("UNSUPPORTED_READINESS", "Готовність заявлена без цільової поведінки.")
        if not briefing.get("verification"):
            add("NO_ACCEPTANCE_TESTS", "Готовність заявлена без перевірок приймання.")
        if briefing.get("unknownsUk"):
            add("READY_WITH_UNKNOWNS", "Позначена готовність попри відкриті питання.")
    if briefing.get("readiness") == "READY_FOR_REVIEW" and any(
            item["status"] == "UNAVAILABLE" for item in briefing.get("sourceAudit", [])):
        add("READY_WITH_UNREAD_SOURCES", "Брифінг заявляє готовність, але частина джерел недоступна.")
    if not briefing.get("timeline") and context and context.get("comments"):
        add("TIMELINE_MISSING", "Є коментарі Jira, але історію рішень не відновлено.")
    return warnings
