"""Opt-in, on-device aggregate BA handoff and wrong-priority metrics.

No task keys, people, free text, exact timestamps, event lists or network.
The operator manually enters measured elapsed seconds and priority corrections.
This NEVER changes official Jira priority, sorting, or AI models.
"""
import argparse
import json
import os
import secrets
import stat
import sys
from pathlib import Path

from app_config import ROOT
from pipeline_lock import pipeline_lock, replace_file

ARCHETYPES = (
    "ERROR_TRIAGE", "SUPPLIER_QUESTION", "REBOOKING",
    "REFUND_REISSUE", "API_ANALYSIS", "EMAIL_HANDOFF",
)
BANDS = ("LOW", "MEDIUM", "HIGH")
REASONS = ("IMPACT", "URGENCY", "DEPENDENCY", "EFFORT", "STALE_CONTEXT")
CONSENT = "SAVE LOCAL BA METRIC"
FILE_NAME = "handoff_aggregate_v1.json"


def _path(root, create=False):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("A normal local BA Desk folder is required")
    base = root / "data"
    if base.is_symlink():
        raise ValueError("Unsafe local data directory")
    if create:
        base.mkdir(mode=0o700, exist_ok=True)
    if not base.is_dir():
        return None
    private = base / "private_metrics"
    if private.is_symlink():
        raise ValueError("Unsafe metrics folder")
    if create:
        private.mkdir(mode=0o700, exist_ok=True)
    if not private.is_dir():
        return None
    if os.name != "nt":
        mode = private.stat().st_mode
        if private.stat().st_uid != os.getuid() or stat.S_IMODE(mode) & 0o077:
            raise ValueError("Private metrics folder has unsafe access mode")
    path = private / FILE_NAME
    if path.is_symlink():
        raise ValueError("Unsafe metrics file")
    return path


def _blank():
    return {"schemaVersion": 1,
            "handoff": {name: {"count": 0, "sumSeconds": 0} for name in ARCHETYPES},
            "priorityFeedback": {reason: 0 for reason in REASONS},
            "bandCorrections": {f"{a}_TO_{b}": 0 for a in BANDS for b in BANDS if a != b}}


def _load(path):
    if path is None or not path.exists():
        return _blank()
    if not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("Invalid aggregate file")
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    template = _blank()
    if not isinstance(value, dict) or set(value) != set(template):
        raise ValueError("Invalid local metrics schema")
    if value["schemaVersion"] != 1:
        raise ValueError("Unsupported local metric schema")
    for field in ("handoff", "priorityFeedback", "bandCorrections"):
        if not isinstance(value[field], dict) or set(value[field]) != set(template[field]):
            raise ValueError("Unrecognized metric categories")
    for entry in value["handoff"].values():
        if (not isinstance(entry, dict) or set(entry) != {"count", "sumSeconds"} or
                any(type(x) is not int or x < 0 for x in entry.values())):
            raise ValueError("Invalid elapsed-time aggregate")
    for field in ("priorityFeedback", "bandCorrections"):
        if any(type(x) is not int or x < 0 for x in value[field].values()):
            raise ValueError("Invalid priority correction aggregate")
    return value


def _save(path, value):
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".pending")
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def record_handoff(root, archetype, seconds, confirm):
    if confirm != CONSENT or archetype not in ARCHETYPES or type(seconds) is not int or not 1 <= seconds <= 28800:
        raise ValueError("Explicit consent, approved archetype and bounded duration required")
    with pipeline_lock(root):
        path = _path(root, create=True)
        value = _load(path)
        cell = value["handoff"][archetype]
        cell["count"] += 1
        cell["sumSeconds"] += seconds
        _save(path, value)
        return summary_from(value)


def record_correction(root, before, after, reason, confirm):
    if (confirm != CONSENT or before not in BANDS or after not in BANDS or
            before == after or reason not in REASONS):
        raise ValueError("Explicit consent and valid manual correction required")
    with pipeline_lock(root):
        path = _path(root, create=True)
        value = _load(path)
        value["priorityFeedback"][reason] += 1
        value["bandCorrections"][f"{before}_TO_{after}"] += 1
        _save(path, value)
        return summary_from(value)


def summary_from(value):
    handoff = {}
    for name, cell in value["handoff"].items():
        count = cell["count"]
        handoff[name] = {
            "count": count,
            "avgSeconds": round(cell["sumSeconds"] / count) if count else None
        }
    return {
        "schemaVersion": 1, "optInLocalOnly": True,
        "noTaskIdentifiersStored": True, "noAutomaticPriorityChanges": True,
        "windowsAclVerified": False, "cloudTelemetry": False,
        "handoffByArchetype": handoff,
        "wrongPriorityReasons": dict(value["priorityFeedback"]),
        "manualBandCorrections": dict(value["bandCorrections"]),
    }


def summary(root=ROOT):
    return summary_from(_load(_path(root)))


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid local metrics arguments")


def main(argv=None):
    parser = _SanitizedParser(description=__doc__)
    parser.add_argument("action", choices=("summary", "handoff", "correction"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--archetype", default="")
    parser.add_argument("--seconds", type=int)
    parser.add_argument("--from-band", default="")
    parser.add_argument("--to-band", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--confirm", default="")
    try:
        args = parser.parse_args(argv)
        if args.action == "summary":
            result = summary(args.root)
        elif args.action == "handoff":
            result = record_handoff(args.root, args.archetype, args.seconds, args.confirm)
        else:
            result = record_correction(
                args.root, args.from_band, args.to_band, args.reason, args.confirm)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError):
        print("Local metrics unavailable: check consent, selection and privacy settings.",
              file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
