"""Synthetic-only SQLite local dashboard read benchmark; never uses real Jira files.

Usage: python performance_smoke.py --sizes 100 500 1000 --iterations 25
Reports p50/p95 and JSON bytes, not a universal performance guarantee.
"""
import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from desk_store import Desk


def synthetic_document(count):
    if not 1 <= count <= 3000:
        raise ValueError("Synthetic task count must be 1..3000.")
    return {"generatedAt": "2026-10-25T10:00:00+00:00",
            "tasks": [{
                "key": f"CCON-{i+1}",
                "summary": f"FAKE Supplier. REST method. Dummy issue {i+1}",
                "jiraStatus": "In Progress",
                "activeSprint": i % 2 == 0,
                "activeSprintStatus": "VERIFIED",
                "analysis": {
                    "signal": "READY", "reasonUk": "Синтетична перевірка.",
                    "nextActionUk": "Зіставити очікувані поля.",
                    "queueScore": 50,
                    "standardDescription": (
                        "#### To Do\\nIF StatusCode=CANCELLED AND DeliveryStatusCode=REMOVED "
                        "THEN omit segment.\\n#### QA\\nCheck positive and negative cases. " * 6),
                },
            } for i in range(count)]}


def percentile(samples, level):
    return sorted(samples)[min(len(samples) - 1, max(0, round((len(samples) - 1) * level)))]


def measure(count, iterations=25):
    if not 3 <= iterations <= 200:
        raise ValueError("Iterations must be 3..200.")
    with tempfile.TemporaryDirectory(prefix="ccon-fake-perf-") as folder:
        root = Path(folder)
        store = Desk(root)
        source = store.inbox / "CCON_BA_Snapshot.json"
        source.write_text(json.dumps(synthetic_document(count)), encoding="utf-8")
        store.import_snapshot()
        summary = {}
        for name, reader in (("full", store.view), ("revision", store.revision),
                             ("serializedHttp", store.view_json_bytes)):
            # Warm up disk caches/SQLite before measuring p50/p95.
            reader()
            times = []
            output = {}
            for _ in range(iterations):
                start = time.perf_counter()
                output = reader()
                times.append(1000 * (time.perf_counter() - start))
            summary[name] = {
                "p50Ms": round(statistics.median(times), 3),
                "p95Ms": round(percentile(times, .95), 3),
                "responseBytes": len(output) if isinstance(output, bytes) else
                    len(json.dumps(output, ensure_ascii=False).encode("utf-8")),
            }
        return {"syntheticTasks": count, "iterations": iterations,
                "full": summary["full"], "revision": summary["revision"],
                "serializedHttp": summary["serializedHttp"],
                "note": "Local SQLite/object/serialized HTTP bytes only; no browser/render/real Jira benchmark."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes", nargs="+", type=int, default=[100, 500, 1000])
    p.add_argument("--iterations", type=int, default=25)
    args = p.parse_args()
    result = [measure(size, args.iterations) for size in args.sizes]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
