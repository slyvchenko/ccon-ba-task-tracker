"""Time-labeled recurrence of error codes in distinct downloaded flows.

Times are taken ONLY from explicit timestamped payload events. An event
timestamp for a flow is not proof that the error occurred at that moment.
Never infer live production error frequency or root-cause ownership.
"""
from datetime import datetime, timezone
from collections import defaultdict


def parse_utc(value):
    if not isinstance(value, str) or len(value) > 45:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def event_window(manifest):
    """UTC flow-event window, deliberately not an error-origin timestamp."""
    diagnostics = manifest.get("flowDiagnostics") or {}
    entries = diagnostics.get("timeline") or []
    times = []
    for row in entries[:200]:
        if not isinstance(row, dict):
            continue
        dt = parse_utc(row.get("eventTimeUtc"))
        if dt is not None:
            times.append(dt)
    if not times:
        return None
    return min(times), max(times)


def recurrence_window(cases, *, max_groups=30):
    """Cases must already be unique validated per-flow selected-supplier rows.

    Each row contains a bounded error-code list and optional flow-event window.
    This helper is pure and does not read corporate payload values.
    """
    grouped = defaultdict(list)
    for row in cases:
        for code in row["codes"]:
            grouped[code].append(row)
    result = {}
    for code, records in grouped.items():
        if len(records) < 2:
            continue
        windows = [x["eventWindow"] for x in records if x.get("eventWindow")]
        days = sorted({dt.date().isoformat() for window in windows for dt in window})
        first = min((window[0] for window in windows), default=None)
        last = max((window[1] for window in windows), default=None)
        result[code] = {
            "distinctFlowCount": len(records),
            "flowsWithExplicitEventTimes": len(windows),
            "firstFlowEventUtc": first.isoformat() if first else None,
            "lastFlowEventUtc": last.isoformat() if last else None,
            "observedFlowEventDaysUtc": days[:60],
            "crossDaySignal": ("OBSERVED_IN_DISTINCT_DOWNLOADED_FLOW_WINDOWS"
                               if len(days) >= 2 and len(windows) >= 2
                               else "TIME_EVIDENCE_INSUFFICIENT"),
            "timeBasis": "EXPLICIT_PAYLOAD_FLOW_EVENTS_NOT_ERROR_TIMESTAMPS",
            "limits": "Local selected-flow sample only; not prevalence or proof of onset.",
        }
    selected = sorted(result, key=lambda code: (-result[code]["distinctFlowCount"], code))
    return {code: result[code] for code in selected[:max_groups]}
