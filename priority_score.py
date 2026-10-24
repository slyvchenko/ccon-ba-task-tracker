"""Deterministic, explainable 0–100 BA work scoring.

This never overrides the active-sprint lane or manual DONE/WAIT classification.
AI proposes individual factor values, which are validated, summed and displayed;
it cannot choose a total score inconsistent with the reported factors.
"""

FACTORS = {
    "businessImpact": 25,
    "urgency": 25,
    "dependencies": 20,
    "baDecision": 20,
    "actionability": 10,
}


def validate_priority_factors(value, score=None):
    if not isinstance(value, dict) or set(value) != set(FACTORS):
        raise ValueError("analysis.priorityFactors requires exactly: " + ", ".join(FACTORS))
    for name, limit in FACTORS.items():
        number = value[name]
        if type(number) is not int or not 0 <= number <= limit:
            raise ValueError(f"analysis.priorityFactors.{name} must be an integer from 0 to {limit}.")
    total = sum(value.values())
    if score is not None and (type(score) not in (int, float) or total != score):
        raise ValueError("analysis.queueScore must equal the sum of priorityFactors.")
    return total


def factor_summary(value):
    total = validate_priority_factors(value)
    return {"score": total, "max": 100,
            "factors": [
                {"name": name, "value": value[name], "max": maximum}
                for name, maximum in FACTORS.items()
            ]}
