"""Non-blocking score consistency checks across daily BA analyses.

A changed score is not proof of AI bias. Analyst judgement and time-sensitive
urgency can change without edits to Jira; the report only flags review candidates.
This module NEVER modifies queue ranking, manual state or Jira data.
"""
import math

DRIFT_REVIEW_POINTS = 20


def finite_score(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100


def inspect_priority(key, previous, current, *, source_changed, sprint_changed):
    """Return score deltas and explicit audit warnings, not automatic corrections."""
    previous = previous if isinstance(previous, dict) else {}
    old = previous.get("queueScore")
    new = current.get("queueScore")
    prior_valid, current_valid = finite_score(old), finite_score(new)
    changed_fields = []
    warnings = []
    delta = None

    if previous and old != new:
        changed_fields.append("queueScore")
    if previous and previous.get("priorityFactors") != current.get("priorityFactors"):
        changed_fields.append("priorityFactors")

    if current_valid and not isinstance(current.get("priorityFactors"), dict):
        warnings.append({
            "key": key, "code": "PRIORITY_FACTORS_MISSING",
            "messageUk": "Оцінка 0–100 не має пояснення через п’ять факторів. Це потребує ручної перевірки.",
        })

    if prior_valid and current_valid and old != new:
        delta = {"before": old, "after": new, "delta": round(new - old, 2)}
        same_verified_context = bool(
            previous.get("contextFingerprint")
            and previous.get("contextFingerprint") == current.get("contextFingerprint"))
        if (same_verified_context and not source_changed and not sprint_changed
                and abs(new - old) >= DRIFT_REVIEW_POINTS):
            warnings.append({
                "key": key, "code": "PRIORITY_DRIFT_REVIEW",
                "messageUk": (
                    f"Оцінка змінилася з {old} на {new} без зміни fingerprint Jira "
                    "або статусу спринту. Це сигнал для ручної перевірки, не доказ помилки."
                ),
            })

    return {"changedFields": changed_fields, "change": delta, "warnings": warnings}
