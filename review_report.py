"""Deterministic daily BA change report and non-blocking quality diagnostics."""
from collections import Counter
from urllib.parse import urlparse
from pathlib import Path

from storage import write_json
from ba_briefing import audit_briefing
from app_config import LIMIT

# A delta may contain both a prior and current 5 MiB question set.
REPORT_LIMIT = 2 * LIMIT + 2 * 1024 * 1024


def normalize(value):
    if value is None:
        return ""
    return " ".join(str(value).split()).casefold()


def normalize_technical(value):
    """Collapse formatting but preserve case-sensitive field names and payloads."""
    return "" if value is None else " ".join(str(value).split())


def has_usable_evidence(analysis):
    """Reject empty or scheme-less evidence before suppressing warnings."""
    for item in analysis.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if isinstance(url, str):
            parsed = urlparse(url.strip())
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return True
    return False


def questions(analysis):
    return {normalize(value): value.strip() for value in analysis.get("missingInfo", [])
            if isinstance(value, str) and value.strip()}


def normalize_briefing(briefing):
    if not briefing:
        return None
    # Preserve semantic ordering of decisions/rules; ignore cosmetic whitespace.
    import json
    return normalize_technical(json.dumps(briefing, ensure_ascii=False, sort_keys=True))


def signature(analysis):
    draft = analysis.get("emailDraft") or {}
    return {
        "signal": analysis.get("signal"),
        "waitingRequired": analysis.get("waitingRequired"),
        "needsEmail": analysis.get("needsEmail"),
        "waitingOnUk": normalize(analysis.get("waitingOnUk")),
        "nextActionUk": normalize(analysis.get("nextActionUk")),
        "missingInfo": tuple(sorted(questions(analysis))),
        "standardDescription": normalize_technical(analysis.get("standardDescription")),
        "briefing": normalize_briefing(analysis.get("briefing")),
        "emailDraft": tuple(normalize_technical(draft.get(field)) for field in ("to", "subject", "body")),
    }


def diagnostics(key, analysis):
    signal = analysis.get("signal")
    proof = has_usable_evidence(analysis)
    findings = []
    def add(code, explanation):
        findings.append({"key": key, "code": code, "messageUk": explanation})
    if signal == "WAIT" and (analysis.get("waitingRequired") is not True or not proof):
        add("WAIT_NOT_VERIFIED", "Очікування потребує підтвердженого джерела й waitingRequired=true.")
    if signal == "WRITE" and analysis.get("needsEmail") is not True:
        add("WRITE_EMAIL_CONFLICT", "Дія WRITE не узгоджена з needsEmail=true.")
    if signal == "DONE" and questions(analysis):
        add("DONE_HAS_QUESTIONS", "Задача DONE, але залишилися відкриті BA-питання.")
    if signal in ("READY", "WRITE", "DECIDE") and not proof:
        add("ACTION_WITHOUT_EVIDENCE", "Запропонована дія не має посилань на перевірені джерела.")
    description = analysis.get("standardDescription") or ""
    if description.strip() and "#### QA" not in description:
        add("DESCRIPTION_WITHOUT_QA", "Чернетка опису не має секції #### QA.")
    return findings


def build_report(previous_tasks, current_tasks, generated_at, left_scope=None, issue_contexts=None):
    """Compare the last imported analysis to today's complete analyzed snapshot.

    Removed questions are *not* called answered: only source review can confirm that.
    Manual statuses are never interpreted as machine-derived task completion.
    """
    totals = Counter()
    changes = []
    warnings = []
    for task in current_tasks:
        key = task["key"]
        analysis = task["analysis"]
        old = previous_tasks.get(key) or {}
        before = old.get("analysis") if isinstance(old.get("analysis"), dict) else {}
        before_questions, after_questions = questions(before), questions(analysis)
        added_keys = sorted(after_questions.keys() - before_questions.keys())
        removed_keys = sorted(before_questions.keys() - after_questions.keys())
        before_signature, after_signature = signature(before), signature(analysis)
        fields = sorted(field for field in after_signature
                        if before and before_signature[field] != after_signature[field])
        old_signal, new_signal = before.get("signal"), analysis.get("signal")
        old_fingerprint = before.get("contextFingerprint")
        source_changed = bool(old_fingerprint and old_fingerprint != task.get("contextFingerprint"))
        sprint_changed = bool(old and
                              old.get("activeSprint") != task.get("activeSprint"))
        if not before or not old_signal:
            category = "NEW"
        elif old_signal != "DONE" and new_signal == "DONE":
            category = "COMPLETED"
        elif old_signal == "DONE" and new_signal != "DONE":
            category = "REOPENED"
        elif fields or source_changed or sprint_changed:
            category = "UPDATED"
        else:
            category = "UNCHANGED"
        totals[category] += 1
        totals["questionsAdded"] += len(added_keys)
        totals["questionsRemoved"] += len(removed_keys)
        changes.append({
            "key": key, "summary": task.get("summary", ""), "url": task.get("url", ""),
            "category": category, "previousSignal": old_signal, "signal": new_signal,
            "sourceChanged": source_changed, "sprintChanged": sprint_changed,
            "activeSprint": task.get("activeSprint"), "changedFields": fields,
            "questionsAdded": [after_questions[value] for value in added_keys],
            "questionsRemoved": [before_questions[value] for value in removed_keys],
            "nextActionUk": analysis.get("nextActionUk", ""),
            "manualStatus": old.get("manualStatus", "AUTO"),
        })
        warnings.extend(diagnostics(key, analysis))
        warnings.extend({"key": key, **warning} for warning in audit_briefing(
            analysis, (issue_contexts or {}).get(key)))
    # Jira results exclude Done by design; an issue leaving JQL is not automatically Done.
    # Only explicit source verification may set JIRA_DONE.
    current_keys = {item["key"] for item in current_tasks}
    disappeared = {item["key"]: item for item in (left_scope or [])}
    # Pending verifications are authoritative even if a running dashboard
    # already marked the issue inactive. Do not re-report old archived tasks.
    keys_to_report = set(disappeared)
    keys_to_report.update(
        key for key, task in previous_tasks.items()
        if key not in current_keys and task.get("active") is True)
    for key in sorted(keys_to_report - current_keys):
        previous = previous_tasks.get(key) or {"key": key}
        status = disappeared.get(key, {})
        verified = status.get("verification") == "VERIFIED"
        done = verified and status.get("confirmedDone") is True
        category = "JIRA_DONE" if done else "LEFT_SCOPE"
        totals[category] += 1
        changes.append({
            "key": key, "summary": previous.get("summary", ""),
            "url": status.get("sourceUrl") or previous.get("url", ""),
            "category": category, "previousSignal": (previous.get("analysis") or {}).get("signal"),
            "signal": None, "sourceChanged": True, "sprintChanged": False,
            "activeSprint": None, "changedFields": ["jiraStatus"],
            "questionsAdded": [], "questionsRemoved": [],
            "nextActionUk": ("Завершення підтверджено категорією Done у Jira." if done else
                             "Перевірити, чому задача вийшла з Jira JQL; це не доводить Done."),
            "manualStatus": previous.get("manualStatus", "AUTO"),
            "jiraStatus": status.get("jiraStatus", ""),
            "jiraVerification": status.get("verification", "UNVERIFIED"),
        })
        if not done:
            warnings.append({"key": key, "code": "LEFT_SCOPE_NOT_DONE",
                             "messageUk": "Задача зникла з JQL, але завершення в Jira не підтверджено."})
    result = {
        "generatedAt": generated_at,
        "summary": {
            "total": len(current_tasks),
            **{category: totals[category] for category in
               ("NEW", "UPDATED", "COMPLETED", "REOPENED", "UNCHANGED")},
            "JIRA_DONE": totals["JIRA_DONE"],
            "LEFT_SCOPE": totals["LEFT_SCOPE"],
            "questionsAdded": totals["questionsAdded"],
            "questionsRemoved": totals["questionsRemoved"],
            "warnings": len(warnings),
        },
        "changes": changes,
        "warnings": warnings,
    }
    return result


def validate_report(report):
    """Both report endpoints require the same complete bounded structure."""
    if not isinstance(report, dict) or not isinstance(report.get("generatedAt"), str):
        raise ValueError("Report timestamp missing.")
    summary = report.get("summary")
    required = ("total", "NEW", "UPDATED", "COMPLETED", "REOPENED", "UNCHANGED",
                "questionsAdded", "questionsRemoved", "warnings")
    if not isinstance(summary, dict) or any(type(summary.get(k)) is not int or
        summary[k] < 0 for k in required):
        raise ValueError("Report summary is incomplete.")
    if not isinstance(report.get("changes"), list) or not isinstance(report.get("warnings"), list):
        raise ValueError("Report changes/warnings are invalid.")
    for item in report["changes"]:
        if not isinstance(item, dict) or any(field not in item for field in
            ("key", "category", "summary", "previousSignal", "signal", "nextActionUk",
             "questionsAdded", "questionsRemoved", "sourceChanged", "url")):
            raise ValueError("Report change is incomplete.")
        if not isinstance(item["questionsAdded"], list) or not isinstance(item["questionsRemoved"], list):
            raise ValueError("Report question lists are invalid.")
    for item in report["warnings"]:
        if not isinstance(item, dict) or any(field not in item for field in
            ("key", "code", "messageUk")):
            raise ValueError("Report warning is incomplete.")
    return report


def render_markdown(report):
    validate_report(report)
    s = report["summary"]
    lines = [
        "# CCON BA Desk: щоденний звіт",
        "",
        "Дата (UTC): " + report["generatedAt"],
        "",
        f"Задач: {s['total']} | Нових: {s['NEW']} | Оновлених: {s['UPDATED']} | "
        f"Завершено за аналізом: {s['COMPLETED']} | Підтверджено Done у Jira: {s.get('JIRA_DONE', 0)} | Поза вибіркою: {s.get('LEFT_SCOPE', 0)} | Повернутих: {s['REOPENED']} | "
        f"Без змін: {s['UNCHANGED']}",
        f"Нових питань: {s['questionsAdded']} | Знятих питань: {s['questionsRemoved']} | "
        f"Попереджень перевірки: {s['warnings']}",
        "",
        "Зняте питання не обов'язково отримало відповідь: потрібна перевірка джерела.",
        "Ручний статус користувача має пріоритет над автоматичними сигналами.",
        "",
        "## Суттєві зміни",
    ]
    changed = [item for item in report["changes"] if item["category"] != "UNCHANGED"]
    if not changed:
        lines.append("Суттєвих змін немає.")
    for item in changed:
        lines += [
            "",
            f"### {item['key']} · {item['category']} · {item['summary']}",
            f"Сигнал: {item['previousSignal'] or 'немає'} → {item['signal']}",
            f"Наступна дія: {item['nextActionUk']}",
        ]
        if item["url"]:
            lines.append("Jira: " + item["url"])
        if item["sourceChanged"]:
            lines.append("Джерела Jira змінилися від останнього аналізу.")
        if item.get("sprintChanged"):
            lines.append("Належність до активного спринту змінилася.")
        for question in item["questionsAdded"]:
            lines.append("+ Нове питання: " + question)
        for question in item["questionsRemoved"]:
            lines.append("- Зняте питання (перевірити підставу): " + question)
    lines += ["", "## Попередження якості"]
    if not report["warnings"]:
        lines.append("Автоматичні перевірки не виявили суперечностей.")
    for item in report["warnings"]:
        lines.append(f"- {item['key']} [{item['code']}]: {item['messageUk']}")
    return "\n".join(lines) + "\n"


def write_report(report, root):
    validate_report(report)
    destination = Path(root) / "data" / "daily_review_report.json"
    write_json(destination, report, REPORT_LIMIT)
    return destination
