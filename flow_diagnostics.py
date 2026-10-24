"""Read-only REST/supplier contract-shape and timestamp diagnostics for one ZIP.

Only the selected supplier, REST, and errors are examined. Raw scalar values,
credentials and passenger data never appear in the persisted report. A ZIP
entry's modified time or numeric filename sequence is NOT an event timestamp.
"""
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import PurePosixPath
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from layered_evidence import classify, file_kind, MAX_SAMPLE
from supplier_logs import XML_NAME

MAX_EXCHANGES = 60
MAX_SHAPE_FIELDS = 110
TIMESTAMP_NAMES = {"timestamp", "eventtime", "eventtimestamp", "loggedat",
                   "logtime", "createdat", "datetime", "receivedat", "sentat"}
ALLOWED = {".json", ".xml", ".soap", ".log", ".txt"}
ISO = re.compile(r"^\d{4}-\d\d-\d\d[Tt ]\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:?\d\d)$")


def event_timestamp(value):
    """Only offset-aware ISO timestamps are safe to order chronologically."""
    if not isinstance(value, str) or len(value) > 40 or not ISO.fullmatch(value):
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return None
        return instant.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _local(name):
    return name.split("}")[-1].split(":")[-1]


def shape_and_times(raw, suffix):
    """Extract field presence, null/repetition hints, and explicit event times only."""
    if len(raw) > MAX_SAMPLE:
        return {"fields": [], "nullFields": [], "repeatedFields": [],
                "eventTimes": [], "parseStatus": "TOO_LARGE"}
    decoded = raw.decode("utf-8-sig", errors="replace")
    fields, nulls, repeats, times = set(), set(), set(), set()
    if suffix == ".json":
        try:
            data = json.loads(decoded)
        except ValueError:
            return {"fields": [], "nullFields": [], "repeatedFields": [],
                    "eventTimes": [], "parseStatus": "INVALID_JSON"}
        def visit(node, prefix="", depth=0):
            if depth > 12 or len(fields) >= MAX_SHAPE_FIELDS:
                return
            if isinstance(node, dict):
                for k, child in list(node.items())[:140]:
                    name = str(k)[:80]
                    path = (prefix + "." if prefix else "") + name
                    fields.add(path)
                    if child is None:
                        nulls.add(path)
                    if name.casefold() in TIMESTAMP_NAMES and isinstance(child, str):
                        stamped = event_timestamp(child)
                        if stamped:
                            times.add(stamped)
                    visit(child, path, depth + 1)
            elif isinstance(node, list):
                if len(node) > 1:
                    repeats.add(prefix)
                for child in node[:4]:
                    visit(child, prefix + "[]", depth + 1)
        visit(data)
    elif suffix in (".xml", ".soap"):
        if "<!DOCTYPE" in decoded.upper() or "<!ENTITY" in decoded.upper():
            return {"fields": [], "nullFields": [], "repeatedFields": [],
                    "eventTimes": [], "parseStatus": "XML_ENTITY_REJECTED"}
        try:
            root = ET.fromstring(decoded)
        except ET.ParseError:
            return {"fields": [], "nullFields": [], "repeatedFields": [],
                    "eventTimes": [], "parseStatus": "INVALID_XML"}
        def visit(element, prefix="", depth=0):
            if depth > 12 or len(fields) >= MAX_SHAPE_FIELDS:
                return
            tag = _local(element.tag)[:80]
            path = (prefix + "." if prefix else "") + tag
            fields.add(path)
            for k, v in list(element.attrib.items())[:12]:
                key = _local(k)[:80]
                fields.add(path + ".@" + key)
                if key.casefold() in TIMESTAMP_NAMES:
                    stamped = event_timestamp(v)
                    if stamped:
                        times.add(stamped)
            if tag.casefold() in TIMESTAMP_NAMES:
                stamped = event_timestamp((element.text or "").strip())
                if stamped:
                    times.add(stamped)
            if element.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                nulls.add(path)
            child_counts = defaultdict(int)
            for child in list(element)[:150]:
                child_counts[_local(child.tag)] += 1
                visit(child, path, depth + 1)
            for name, count in child_counts.items():
                if count > 1:
                    repeats.add(path + "." + name[:80])
        visit(root)
    else:
        # Text/log content is not a structured contract source.
        return {"fields": [], "nullFields": [], "repeatedFields": [],
                "eventTimes": [], "parseStatus": "UNSTRUCTURED_LOG"}
    return {"fields": sorted(fields)[:MAX_SHAPE_FIELDS],
            "nullFields": sorted(nulls)[:MAX_SHAPE_FIELDS],
            "repeatedFields": sorted(repeats)[:MAX_SHAPE_FIELDS],
            "eventTimes": sorted(times)[:12], "parseStatus": "PARSED"}


def supplier_method(path):
    match = XML_NAME.fullmatch(path.name)
    if match:
        return {"operation": match["operation"][:100],
                "method": match["method"][:100],
                "supplierSequence": int(match["seq"])}
    return {"operation": None, "method": None, "supplierSequence": None}


def diagnose_zip(raw, supplier, value_review=None):
    """Use after layered_evidence ZIP safety checks; cannot fetch remote data."""
    aliases = supplier["aliases"]
    entries, warnings = [], []
    with ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 512 * 1024 * 1024:
            raise ValueError("ZIP expansion limit.")
        for order, info in enumerate(infos):
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or any(":" in p for p in path.parts):
                raise ValueError("Unsafe ZIP entry.")
            layer = classify(path, aliases)
            if layer not in ("supplier", "rest", "errors") or path.suffix.casefold() not in ALLOWED:
                continue
            if len(entries) >= MAX_EXCHANGES:
                warnings.append("ENTRY_LIMIT_REACHED")
                break
            if info.file_size > MAX_SAMPLE:
                shape = {"fields": [], "nullFields": [], "repeatedFields": [],
                         "eventTimes": [], "parseStatus": "TOO_LARGE"}
            else:
                shape = shape_and_times(archive.read(info), path.suffix.casefold())
            method = supplier_method(path) if layer == "supplier" else {
                "operation": None, "method": None, "supplierSequence": None}
            entries.append({
                "id": len(entries) + 1, "file": str(path)[:300], "layer": layer,
                "direction": file_kind(path), "zipOrder": order,
                "eventTimeUtc": shape["eventTimes"][0] if len(shape["eventTimes"]) == 1 else None,
                "timeEvidence": ("PAYLOAD_TIMESTAMP" if len(shape["eventTimes"]) == 1
                                 else "MULTIPLE_TIMES_AMBIGUOUS" if shape["eventTimes"]
                                 else "NO_EVENT_TIMESTAMP"),
                "method": method["method"], "operation": method["operation"],
                "sequenceHint": method["supplierSequence"],
                "shape": {k: shape[k] for k in ("fields", "nullFields", "repeatedFields")},
                "parseStatus": shape["parseStatus"],
            })
    # Build a contract candidate from independent direction-specific value
    # comparisons. No assertion that repeated paths or null are bugs.
    contract = []
    by_file = {x["file"]: x for x in entries}
    for item in (value_review or {}).get("comparisons", [])[:30]:
        if not isinstance(item, dict):
            continue
        supplier_item = by_file.get(item.get("supplierFile"))
        rest_item = by_file.get(item.get("restFile"))
        if not supplier_item or not rest_item:
            warnings.append("MAPPING_FILE_NOT_IN_SAMPLE")
            continue
        rest_fields = set(rest_item["shape"]["fields"])
        supplier_fields = set(supplier_item["shape"]["fields"])
        contract.append({
            "direction": item.get("direction"),
            "restFile": rest_item["file"], "supplierFile": supplier_item["file"],
            "restOperation": "UNVERIFIED_IN_ZIP",
            "supplierOperation": supplier_item["operation"],
            "supplierMethod": supplier_item["method"],
            "mappingStatus": "CANDIDATE_NOT_CONFIRMED_CONTRACT",
            "pairingBasis": item.get("pairingBasis"),
            "exactValueCandidates": (item.get("exactValueCandidates") or [])[:25],
            "differentValueCandidates": (item.get("sameNamedDifferentValues") or [])[:25],
            "restNullFields": rest_item["shape"]["nullFields"][:40],
            "supplierNullFields": supplier_item["shape"]["nullFields"][:40],
            "restRepeatedFields": rest_item["shape"]["repeatedFields"][:40],
            "supplierRepeatedFields": supplier_item["shape"]["repeatedFields"][:40],
            "restFieldCount": len(rest_fields),
            "supplierFieldCount": len(supplier_fields),
        })
    # Only payload timestamps can order events. ZIP order and supplier
    # sequence are retained as hints but NOT used to infer causal order.
    timeline = sorted(entries, key=lambda x: (
        x["eventTimeUtc"] is None, x["eventTimeUtc"] or "", x["zipOrder"]))
    seen = defaultdict(list)
    for entry in entries:
        if entry["layer"] == "supplier" and entry["direction"] == "request" and entry["method"]:
            seen[entry["method"]].append(entry)
    repeats = [{
        "supplierMethod": name, "requestCount": len(items),
        "entryIds": [entry["id"] for entry in items],
        "interpretation": "REPEATED_METHOD_RETRY_NOT_PROVEN"
    } for name, items in sorted(seen.items()) if len(items) > 1]
    complete_time = sum(x["eventTimeUtc"] is not None for x in entries)
    if complete_time < len(entries):
        warnings.append("INCOMPLETE_EVENT_TIMESTAMPS_NO_GLOBAL_CHRONOLOGY")
    if any(x["parseStatus"] != "PARSED" for x in entries):
        warnings.append("UNPARSED_OR_UNSTRUCTURED_EXCHANGES")
    return {
        "schemaVersion": 1,
        "supplier": supplier["name"],
        "entriesExamined": len(entries),
        "timestampedEntries": complete_time,
        "timeStatus": ("ALL_EXPLICIT_TIMESTAMPS" if complete_time == len(entries) and entries
                       else "PARTIAL_EXPLICIT_TIMESTAMPS" if complete_time
                       else "NO_EXPLICIT_EVENT_TIMESTAMPS"),
        "timeline": timeline[:MAX_EXCHANGES],
        "contractCandidates": contract[:30],
        "repeatedMethodCandidates": repeats[:20],
        "warnings": sorted(set(warnings)),
        "disclaimer": ("Only explicit offset-aware timestamps determine order. "
                       "ZIP ordering, supplier sequence and repeated methods do not "
                       "prove chronology, causality, retries or a correct mapping contract."),
    }
