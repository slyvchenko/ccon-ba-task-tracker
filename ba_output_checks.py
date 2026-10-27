"""Deterministic human-facing BA dossier and generated-email quality warnings.

These checks do not verify business truth or send emails. They only prevent
machine-written outputs from silently declaring themselves complete while
important source or attachment requirements remain unverified.
"""
import re

ATTACHMENT_CLAIM = re.compile(
    r"(?i)(?:"
    r"\b(?:logs?|zip|evidence|files?)\s+(?:are|is|were)\s+(?:already\s+)?attached\b|"
    r"\b(?:I|we)\s+(?:have|'ve)\s+attached\b|"
    r"\bplease\s+find\b.{0,100}\battached\b|"
    r"\battached\b.{0,65}\b(?:logs?|zip|files?)\b"
    r")")
NEGATED_CLAIM = re.compile(
    r"(?i)\b(?:not|aren't|isn't|weren't|without|no)\b.{0,20}\battached\b|"
    r"\b(?:will|can|could|may)\s+be\s+attached\b|"
    r"\bnot\s+yet\s+attached\b")
METHOD_ASSERTION = re.compile(r"(?i)\bduring\s+(do[A-Z][A-Za-z0-9_]*)\b")
SUBJECT_METHOD_ASSERTION = re.compile(
    r"(?i)^\s*(?:AER\.\s*)?"
    r"(?:(?:CCON-\d+\s*(?:/\s*)?)+\s*[:—–-]?\s*)?"
    r"(do[A-Z][A-Za-z0-9_]*)\b"
)
TECH_LITERAL = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z][A-Za-z0-9_]*Code|SegmentRefID)"
    r"\s*(?:==|=|:)\s*['\"]?([A-Z][A-Z0-9_]{1,70}|[a-z][a-z0-9_]*_[a-z0-9_]+)")
RESERVED = {"AND", "OR", "IF", "THEN", "TRUE", "FALSE", "NULL", "NONE"}


def issue(code, ref, explanation):
    return {"code": code, "ref": ref, "messageUk": explanation}


def dossier_checks(analysis, *, persisted_questions=None):
    findings = []
    briefing = analysis.get("briefing") or {}
    if not isinstance(briefing, dict):
        return findings
    if briefing.get("readiness") != "READY_FOR_REVIEW":
        return findings
    pending = (analysis.get("missingInfo") or [])
    unknowns = briefing.get("unknownsUk") or []
    open_rules = [r for r in (briefing.get("rules") or [])[:30]
                  if isinstance(r, dict) and r.get("certainty") != "CONFIRMED"]
    if any(isinstance(x, str) and x.strip() for x in pending) or any(
            isinstance(x, str) and x.strip() for x in unknowns):
        findings.append(issue(
            "OPEN_REQUIREMENTS_PENDING", "briefing",
            "Заявлено готовність до рев'ю, але залишилися матеріальні відкриті питання."))
    if any(isinstance(q, dict) and q.get("status") == "OPEN"
           for q in (persisted_questions or [])) and not any(
           v["code"] == "OPEN_REQUIREMENTS_PENDING" for v in findings):
        findings.append(issue("OPEN_REQUIREMENTS_PENDING", "briefing",
                              "Збережені BA-питання залишаються відкритими."))
    if open_rules:
        findings.append(issue(
            "OPEN_RULES_PENDING", "briefing",
            "Заявлено готовність до рев'ю за наявності непідтверджених правил."))
    return findings


def technical_literals(when, then):
    """Exact non-PII enum/code literals, not free-text or arbitrary log values."""
    tokens = set()
    for line in (when, then):
        for match in TECH_LITERAL.finditer(str(line or "")):
            value = match.group(1)
            if value.upper() not in RESERVED:
                tokens.add(value)
    return tokens


def email_checks(draft, *, attachment_ready=None, verified_supplier_method=None):
    """Only generated draft, never a human-saved email. No mutation."""
    if not isinstance(draft, dict):
        return []
    findings = []
    body = draft.get("body") if isinstance(draft.get("body"), str) else ""
    subject = draft.get("subject") if isinstance(draft.get("subject"), str) else ""
    if attachment_ready is not True:
        # Unknown readiness is NOT permission to assert a verified archive.
        for line in body.splitlines():
            # A negative statement about the response cannot excuse a
            # separate positive assertion that the request logs are attached.
            clauses = re.split(r"(?<=[.!?;])\s+|\s*;\s*|\s*,\s*but\s+|\s+but\s+", line, flags=re.I)
            if any(ATTACHMENT_CLAIM.search(clause) and not NEGATED_CLAIM.search(clause)
                   for clause in clauses):
                findings.append(issue(
                    "EMAIL_UNVERIFIED_ATTACHMENT_CLAIM", "emailDraft",
                    "Чернетка стверджує наявність вкладення без актуального перевіреного supplier ZIP."))
                break
    if verified_supplier_method and isinstance(verified_supplier_method, str):
        methods = {match.group(1) for match in METHOD_ASSERTION.finditer(body)}
        subject_match = SUBJECT_METHOD_ASSERTION.match(subject)
        if subject_match:
            methods.add(subject_match.group(1))
        if any(method != verified_supplier_method for method in methods):
            findings.append(issue(
                "EMAIL_METHOD_CONFLICT", "emailDraft",
                "У листі вказаний supplier method, який не збігається з перевіреним методом журналу."))
    return findings
