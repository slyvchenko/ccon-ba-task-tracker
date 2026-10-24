"""Deterministic daily BA change report and non-blocking quality diagnostics."""
from collections import Counter
from pathlib import Path

from storage import write_json


def normalize(value):
    if value is None:
        return ""
    return " ".join(str(value).split()).casefold()


def questions(analysis):
    return {normalize(value): value.strip() for value in analysis.get("missingInfo", [])
            if isinstance(value, str) and value.strip()}


def signature(analysis):
    draft = analysis.get("emailDraft") or {}
    return {
        "signal": analysis.get("signal"),
        "waitingRequired": analysis.get("waitingRequired"),
        "needsEmail": analysis.get("needsEmail"),
        "waitingOnUk": normalize(analysis.get("waitingOnUk")),
        "nextActionUk": normalize(analysis.get("nextActionUk")),
        "missingInfo": tuple(sorted(questions(analysis))),
        "standardDescription": normalize(analysis.get("standardDescription")),
        "emailDraft": tuple(normalize(draft.get(field)) for field in ("to", "subject", "body")),
    }


def diagnostics(key, analysis):
    signal = analysis.get("signal")
    proof = analysis.get("evidence") or []
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


def build_report(previous_tasks, current_tasks, generated_at):
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
        if not before or not old_signal:
            category = "NEW"
        elif old_signal != "DONE" and new_signal == "DONE":
            category = "COMPLETED"
        elif old_signal == "DONE" and new_signal != "DONE":
            category = "REOPENED"
        elif fields or source_changed:
            category = "UPDATED"
        else:
            category = "UNCHANGED"
        totals[category] += 1
        totals["questionsAdded"] += len(added_keys)
        totals["questionsRemoved"] += len(removed_keys)
        changes.append({
            "key": key, "summary": task.get("summary", ""), "url": task.get("url", ""),
            "category": category, "previousSignal": old_signal, "signal": new_signal,
            "sourceChanged": source_changed, "changedFields": fields,
            "questionsAdded": [after_questions[value] for value in added_keys],
            "questionsRemoved": [before_questions[value] for value in removed_keys],
            "nextActionUk": analysis.get("nextActionUk", ""),
            "manualStatus": old.get("manualStatus", "AUTO"),
        })
        warnings.extend(diagnostics(key, analysis))
    result = {
        "generatedAt": generated_at,
        "summary": {
            "total": len(current_tasks),
            **{category: totals[category] for category in
               ("NEW", "UPDATED", "COMPLETED", "REOPENED", "UNCHANGED")},
            "questionsAdded": totals["questionsAdded"],
            "questionsRemoved": totals["questionsRemoved"],
            "warnings": len(warnings),
        },
        "changes": changes,
        "warnings": warnings,
    }
    return result


def render_markdown(report):
    s = report["summary"]
    lines = [
        "# CCON BA Desk: щоденний звіт",
        "",
        "Дата (UTC): " + report["generatedAt"],
        "",
        f"Задач: {s['total']} | Нових: {s['NEW']} | Оновлених: {s['UPDATED']} | "
        f"Завершених за аналізом: {s['COMPLETED']} | Повернутих: {s['REOPENED']} | "
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
    destination = Path(root) / "data" / "daily_review_report.json"
    write_json(destination, report)
    return destination
