"""Daily safe prompt calibration from observed diagnostic patterns.

This automatically updates a low-risk adaptive checklist, NOT the reviewed
BA rules or system prompt. No source text/Jira secrets flow into this file.
"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from storage import write_json
from app_config import ROOT

PATTERNS = {
    "WAIT_NOT_VERIFIED": "Перед WAIT знайди поточну датовану домовленість, конкретного власника очікування та URL.",
    "WRITE_EMAIL_CONFLICT": "Перевір узгодженість WRITE, needsEmail і реальної потреби в зовнішній відповіді.",
    "DONE_HAS_QUESTIONS": "Не позначай DONE, поки залишаються критичні незакриті BA-питання.",
    "ACTION_WITHOUT_EVIDENCE": "Кожну дію та критичну вимогу звіряй із прочитаним джерелом; не виводь вигадані посилання.",
    "DESCRIPTION_WITHOUT_QA": "Підготуй перевірювані acceptance checks до кожної погодженої суттєвої зміни.",
    "BRIEF_MISSING": "Підготуй структурований BA-брифінг за BA_DEEP_REVIEW.md для кожної актуальної задачі.",
    "FACT_WITHOUT_SOURCE": "Кожен confirmed fact повинен мати URL справді прочитаного контексту.",
    "RULE_WITHOUT_SOURCE": "Критичні IF/THEN мають точне джерело та збережені логічні AND/OR.",
    "READY_WITH_UNKNOWNS": "Не заявляй READY_FOR_REVIEW, якщо залишилися відкриті питання.",
    "NO_ACCEPTANCE_TESTS": "Готовність до BA review потребує конкретних QA-сценаріїв.",
    "READY_WITH_UNREAD_SOURCES": "Недоступні критичні логи і вкладення блокують заяву про повноту доказів.",
    "LEFT_SCOPE_NOT_DONE": "Якщо Jira-задача зникла з JQL, перевір її реальний statusCategory перед словом 'завершено'.",
}


def compile_calibration(report, reviews=None, date=None):
    if not isinstance(report, dict) or not isinstance(report.get("warnings"), list):
        raise ValueError("Expected validated daily report warnings.")
    counts = Counter(
        item.get("code") for item in report["warnings"]
        if isinstance(item, dict) and item.get("code") in PATTERNS
    )
    ranked = sorted(counts, key=lambda code: (-counts[code], code))
    if date is None:
        try:
            date = datetime.now(ZoneInfo("Europe/Warsaw")).date().isoformat()
        except ZoneInfoNotFoundError:
            # Windows often ships no IANA tzdb; local calendar date is a
            # best-effort fallback for the human-facing checklist only.
            date = datetime.now().astimezone().date().isoformat()
    checklist = [{"code": code, "occurrences": counts[code],
                  "instructionUk": PATTERNS[code]} for code in ranked]
    human_warnings = []
    if isinstance(reviews, dict) and reviews.get("status") == "REVIEWED" and isinstance(reviews.get("metrics"), dict):
        dimensions = reviews["metrics"].get("candidate", {}).get("rubric", {})
        for name, value in sorted(dimensions.items()):
            rate = value.get("goodRate") if isinstance(value, dict) else None
            if isinstance(rate, (int, float)) and 0 <= rate < 0.9:
                human_warnings.append(
                    {"dimension": name, "goodRate": rate,
                     "actionUk": "Є підтверджене відхилення в незалежній оцінці. "
                     "Проведи review невдалих кейсів перед зміною базових правил."}
                )
    return {
        "date": date, "status": "ADAPTIVE_CHECKLIST_NOT_UNREVIEWED_PROMPT_CHANGE",
        "observations": sum(counts.values()), "checklist": checklist,
        "humanQualityWarnings": human_warnings,
        "baselineRuleFiles": ["DAILY_REVIEW.md", "BA_ANALYSIS_RULES.md",
                              "BA_DEEP_REVIEW.md", "TASK_DESCRIPTION_RULES.md"],
    }


def markdown(result):
    lines = [
        "# Щоденне уточнення BA checklist · " + result["date"],
        "",
        "Згенеровано лише з контрольованих кодів перевірки якості.",
        "Цей файл має нижчий пріоритет за базові правила BA.",
        "Не змінюй їх автоматично; зафіксуй пропозицію та перевір її на реальних кейсах.",
        "",
    ]
    if not result["checklist"] and not result["humanQualityWarnings"]:
        lines.append("Нових діагностичних сигналів немає. Чинні BA-правила залишаються без змін.")
    for item in result["checklist"]:
        lines.append(f"- [{item['code']}; {item['occurrences']}] {item['instructionUk']}")
    for item in result["humanQualityWarnings"]:
        lines.append(f"- [HUMAN:{item['dimension']}; {item['goodRate']:.0%}] {item['actionUk']}")
    return "\n".join(lines) + "\n"


def update_daily(report, root=ROOT, reviews=None, date=None):
    document = compile_calibration(report, reviews, date)
    directory = Path(root) / "data" / "prompt_calibration"
    output = directory / ("review_" + document["date"] + ".json")
    write_json(output, document)
    write_json(directory / "current.json", document)
    (directory / "current.md").write_text(markdown(document), encoding="utf-8")
    return document
