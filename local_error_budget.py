"""Opt-in, process-memory-only local HTTP error budget. No identifiers or telemetry.

This is an API response-status estimate, NOT a complete availability SLO:
network failures, browser errors, upstream Jira/Kibana, and process crashes
are outside this mechanism. Never store URLs, issue keys, clients or payloads.
"""
from collections import deque
from threading import Lock
import time

WINDOW_SECONDS = 3600
MAX_SAMPLES = 10000


class LocalErrorBudget:
    def __init__(self, *, clock=None, window_seconds=WINDOW_SECONDS, max_samples=MAX_SAMPLES):
        if not 60 <= window_seconds <= 86400 or not 20 <= max_samples <= 100000:
            raise ValueError("Invalid in-memory sampling limits")
        self._clock = clock or time.monotonic
        self._window = window_seconds
        self._limit = max_samples
        self._lock = Lock()
        self._events = deque()
        self._truncated = False

    def _prune(self, now):
        while self._events and now - self._events[0][0] >= self._window:
            self._events.popleft()

    def record(self, path, status_code, duration_ms):
        # Do not store or export path. Health/metrics are intentionally
        # excluded so checking the dashboard does not improve the SLO.
        if (not isinstance(path, str) or not path.startswith("/api/") or
                path.split("?", 1)[0] in ("/api/error-budget", "/api/health")):
            return
        code = int(status_code)
        if not 100 <= code <= 599:
            return
        elapsed = max(0, min(60000, round(float(duration_ms))))
        with self._lock:
            now = self._clock()
            self._prune(now)
            if len(self._events) >= self._limit:
                self._events.popleft()
                self._truncated = True
            # Only timestamp, numeric response group and coarse latency.
            self._events.append((now, code >= 500, 400 <= code < 500, elapsed))

    def snapshot(self):
        with self._lock:
            self._prune(self._clock())
            count = len(self._events)
            errors = sum(x[1] for x in self._events)
            client = sum(x[2] for x in self._events)
            latencies = sorted(x[3] for x in self._events)
            p95 = latencies[min(count - 1, int((count - 1) * .95))] if count else None
            allowed = count * .01
            return {
                "enabled": True, "localOnly": True, "inMemoryOnly": True,
                "remoteTelemetry": False, "windowMinutes": self._window // 60,
                "sampledApiResponses": count, "server5xx": errors,
                "client4xx": client, "targetSuccessPercent": 99,
                "successPercent": round(100 * (count - errors) / count, 2) if count else None,
                "errorBudgetAllowed": round(allowed, 2),
                "errorBudgetUsed": errors,
                "errorBudgetRemaining": round(max(0, allowed - errors), 2),
                "responseLatencyP95Ms": p95,
                "insufficientSamples": count < 100,
                "sampleTruncated": self._truncated,
                "noFullAvailabilityClaim": True,
                "scope": "Observed local API HTTP statuses only, excluding health and metric requests.",
            }
