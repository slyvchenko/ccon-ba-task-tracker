"""Conservative cleanup and structural density hints for generated BA Jira text.

This is NOT a semantic summarizer. Do not shorten IF/THEN, source references,
technical literals, QA cases or hand-written descriptions. Only exact
immediately repeated nonheading lines are removed, outside fenced examples.
"""
import re

MAX_DESCRIPTION = 120000


def compact_generated(description):
    if not isinstance(description, str) or not description:
        return description, {"exactAdjacentLinesRemoved": 0}
    if len(description) > MAX_DESCRIPTION:
        return description, {"exactAdjacentLinesRemoved": 0, "state": "OVER_LIMIT"}
    output = []
    seen = 0
    in_fence = False
    previous = None
    for line in description.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        ordinary = bool(stripped and len(stripped) >= 25
                        and not stripped.startswith(("#", "```", "~~~")))
        if not in_fence and ordinary and line == previous:
            seen += 1
            continue
        # One empty spacer is sufficient and does not change paragraph content.
        if not in_fence and not stripped and output and not output[-1].strip():
            continue
        output.append(line)
        previous = line if ordinary and not in_fence else None
    return "\n".join(output), {"exactAdjacentLinesRemoved": seen, "state": "NO_SEMANTIC_REWRITE"}


def profile(description):
    """Counts only: no raw phrases, PII, enum values or IDs."""
    if not isinstance(description, str):
        return {"words": 0, "nonemptyLines": 0, "qaChecks": 0,
                "exactRepeatedLines": 0, "longProseLines": 0}
    text = description[:MAX_DESCRIPTION]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized = [line.casefold() for line in lines
                  if len(line) >= 30 and not line.startswith("#")]
    qa_checks = sum(bool(re.match(r"(?i)^[-*]?\s*Check\b", line)) for line in lines)
    return {
        "words": len(re.findall(r"\S+", text)),
        "nonemptyLines": len(lines),
        "qaChecks": qa_checks,
        "exactRepeatedLines": len(normalized) - len(set(normalized)),
        "longProseLines": sum(len(line) > 400 for line in lines if not
                              re.search(r"(?:https?://|\\{|`{3})", line)),
        "state": "COUNTS_ONLY_NOT_SEMANTIC_QUALITY",
    }


def advisory_findings(description):
    """Warn, but never block readiness based on length alone."""
    values = profile(description)
    result = []
    if values["exactRepeatedLines"] >= 2:
        result.append({"code": "DESCRIPTION_REPETITION_REVIEW", "ref": "description",
                       "messageUk": "В описі є повторювані рядки. Перевір чи кожен додає нову вимогу."})
    if values["longProseLines"] >= 2:
        result.append({"code": "DESCRIPTION_LONG_PARAGRAPHS", "ref": "description",
                       "messageUk": "Є дуже довгі рядки. Можна скоротити виклад без втрати технічної логіки."})
    return result
