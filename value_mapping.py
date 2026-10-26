"""Private, bounded REST↔supplier *value-level* comparison without leaking values.

Compare REST requests with supplier requests and supplier responses with REST
responses. Only pair exchanges on shared explicit correlation IDs, or when
exactly one request/response exists per compared layer. This yields mapping
CANDIDATES, never a verified business rule or a proven bug.
Persist paths/counts/boolean differences, not passenger/customer values.
"""
import hashlib
import io
import json
import re
import secrets
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import PurePosixPath
from zipfile import ZipFile

from layered_evidence import classify, file_kind, MAX_CASES, MAX_SAMPLE

MAX_PAIRS = 30
MAX_FIELDS = 220
ID_FIELDS = {"cconflowid", "traceid", "correlationid", "requestid", "conversationid"}
ALLOWED_SUFFIX = {".xml", ".json", ".soap"}
UNINFORMATIVE = {"", "true", "false", "null", "none", "ok", "0", "1"}


def leaf_values(data, suffix):
    """Bounded scalar leaves from safe JSON/XML, ephemeral in memory."""
    if len(data) > MAX_SAMPLE:
        return {}, "PAYLOAD_TOO_LARGE"
    text = data.decode("utf-8-sig", errors="replace")
    if suffix in (".xml", ".soap") or text.lstrip().startswith("<"):
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            return {}, "XML_ENTITIES_DISALLOWED"
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return {}, "INVALID_XML"
        result = {}
        def walk(element, path, depth):
            if depth > 12 or len(result) >= MAX_FIELDS:
                return
            tag = element.tag.rsplit("}", 1)[-1]
            next_path = (path + "." if path else "") + tag[:80]
            children = list(element)
            if not children and element.text and element.text.strip():
                result[next_path] = element.text.strip()[:8000]
            for k, v in list(element.attrib.items())[:20]:
                if len(result) < MAX_FIELDS:
                    result[next_path + ".@" + k[:60]] = v[:8000]
            for child in children[:150]:
                walk(child, next_path, depth + 1)
        walk(root, "", 0)
        return result, None
    if suffix == ".json" or text.lstrip().startswith(("{", "[")):
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            return {}, "INVALID_JSON"
        result = {}
        def walk(node, path, depth):
            if depth > 12 or len(result) >= MAX_FIELDS:
                return
            if isinstance(node, dict):
                for name, value in list(node.items())[:200]:
                    walk(value, (path + "." if path else "") + str(name)[:80], depth + 1)
            elif isinstance(node, list):
                # Array position is not a field identity. Repeated values in
                # arrays are ambiguous, so skip them for mapping candidates.
                if len(node) == 1:
                    walk(node[0], path + "[]", depth + 1)
            elif node is not None and type(node) in (str, int, float, bool):
                result[path] = str(node)[:8000]
        walk(obj, "", 0)
        return result, None
    return {}, "UNSUPPORTED_FORMAT"


def last_field(path):
    return path.rsplit(".", 1)[-1].lstrip("@").casefold().replace("_", "").replace("-", "")


def correlation_tokens(values):
    return {value.casefold() for key, value in values.items()
            if last_field(key) in ID_FIELDS and 8 <= len(value) <= 100
            and re.fullmatch(r"[A-Za-z0-9_.:-]+", value)}


def _useful(value):
    return value.casefold() not in UNINFORMATIVE and len(value) >= 5


def _compare_fields(rest, supplier):
    """Opaque in-memory equality. Never return scalar field values."""
    left = rest["values"]
    right = supplier["values"]
    left_index, right_index = defaultdict(list), defaultdict(list)
    for path, value in left.items():
        if _useful(value):
            left_index[value].append(path)
    for path, value in right.items():
        if _useful(value):
            right_index[value].append(path)
    matches = []
    for value, paths in left_index.items():
        if len(paths) != 1 or len(right_index.get(value, [])) != 1:
            continue
        lkey, rkey = paths[0], right_index[value][0]
        if last_field(lkey) in ID_FIELDS or last_field(rkey) in ID_FIELDS:
            continue
        matches.append({"restField": lkey, "supplierField": rkey,
                        "classification": "EXACT_SCALAR_EQUALITY_CANDIDATE"})
    # Same terminal field names are useful checkpoints even when different:
    # mismatches are not proof of a bug because translation may be intentional.
    left_by_name, right_by_name = defaultdict(list), defaultdict(list)
    for key in left:
        left_by_name[last_field(key)].append(key)
    for key in right:
        right_by_name[last_field(key)].append(key)
    different = []
    for name in left_by_name.keys() & right_by_name.keys():
        if name in ID_FIELDS or len(left_by_name[name]) != 1 or len(right_by_name[name]) != 1:
            continue
        lp, rp = left_by_name[name][0], right_by_name[name][0]
        if left[lp] != right[rp]:
            different.append({"restField": lp, "supplierField": rp,
                              "classification": "DIFFERENT_VALUE_CHECK_TRANSFORM"})
    matches.sort(key=lambda x: (x["restField"], x["supplierField"]))
    different.sort(key=lambda x: (x["restField"], x["supplierField"]))
    return {
        "exactValueCandidates": matches[:35],
        "sameNamedDifferentValues": different[:35],
        "restFields": len(left), "supplierFields": len(right),
        "mappingStatus": "CANDIDATE_ONLY",
    }


def compare_zip_bytes(raw, aliases):
    """Structural alignment plus actual ephemeral field equality comparisons."""
    samples = []
    issues = []
    with ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(x.file_size for x in entries) > 512 * 1024 * 1024:
            raise ValueError("Oversized ZIP.")
        for item in entries:
            if item.is_dir():
                continue
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or any(":" in p for p in path.parts):
                raise ValueError("Unsafe ZIP entry.")
            layer = classify(path, aliases)
            if layer not in ("rest", "supplier") or path.suffix.casefold() not in ALLOWED_SUFFIX:
                continue
            kind = file_kind(path)
            if kind == "unknown":
                continue
            if item.file_size > MAX_SAMPLE:
                issues.append("LARGE_PAYLOAD_NOT_COMPARED")
                continue
            rawfile = archive.read(item)
            values, problem = leaf_values(rawfile, path.suffix.casefold())
            if problem:
                issues.append(problem)
                continue
            if len(samples) >= MAX_CASES * 3:
                issues.append("CASE_LIMIT_REACHED")
                continue
            samples.append({"layer": layer, "kind": kind, "path": str(path)[:300],
                            "values": values, "ids": correlation_tokens(values)})
    result, coverage = [], []
    for rest_kind, supplier_kind, direction in (
        ("request", "request", "REST_REQUEST_TO_SUPPLIER_REQUEST"),
        ("response", "response", "SUPPLIER_RESPONSE_TO_REST_RESPONSE"),
    ):
        rests = [x for x in samples if x["layer"] == "rest" and x["kind"] == rest_kind]
        suppliers = [x for x in samples if x["layer"] == "supplier" and x["kind"] == supplier_kind]
        matched_rest, matched_supplier = set(), set()
        if not rests or not suppliers:
            if rests or suppliers:
                issues.append("INCOMPLETE_EXCHANGE")
        else:
            # Candidate edges are by explicit correlation identifiers only.
            # An unrelated unique RQ/RS must never be paired when both sides
            # explicitly disagree about its identity.
            edges = {}
            for i, r in enumerate(rests):
                edges[i] = [j for j, supplier in enumerate(suppliers)
                            if r["ids"] and supplier["ids"] and
                            r["ids"] & supplier["ids"]]
            for i, rest in enumerate(rests):
                if len(result) >= MAX_PAIRS:
                    issues.append("COMPARISON_PAIR_LIMIT_REACHED")
                    break
                candidates = edges[i]
                if len(candidates) == 1:
                    j = candidates[0]
                    # Reverse uniqueness: two REST exchanges with one shared
                    # supplier trace are NOT two independently proven pairs.
                    if sum(j in xs for xs in edges.values()) != 1:
                        issues.append("AMBIGUOUS_PAIRING")
                        continue
                    basis = "SHARED_CORRELATION_ID"
                elif len(candidates) > 1:
                    issues.append("AMBIGUOUS_PAIRING")
                    continue
                elif len(rests) == len(suppliers) == 1 and not rest["ids"] and not suppliers[0]["ids"]:
                    j, basis = 0, "UNIQUE_SINGLE_EXCHANGE"
                else:
                    # Distinguish explicit contradiction from missing IDs.
                    issues.append("CORRELATION_MISMATCH" if len(rests) == len(suppliers) == 1
                                  and rest["ids"] and suppliers[0]["ids"] else
                                  "UNCORRELATED_EXCHANGE")
                    continue
                supplier = suppliers[j]
                matched_rest.add(i)
                matched_supplier.add(j)
                result.append({
                    "direction": direction, "restFile": rest["path"],
                    "supplierFile": supplier["path"], "pairingBasis": basis,
                    # Equality is NEVER proof of semantic transformation.
                    **_compare_fields(rest, supplier),
                })
        coverage.append({
            "direction": direction,
            "restExchanges": len(rests), "supplierExchanges": len(suppliers),
            "candidatePairs": len(matched_rest),
            "unpairedRest": len(rests) - len(matched_rest),
            "unpairedSupplier": len(suppliers) - len(matched_supplier),
            "state": "CANDIDATE_ONLY" if matched_rest and
                     len(matched_rest) == len(rests) == len(suppliers) else "INCOMPLETE_OR_AMBIGUOUS",
        })
    return {"comparisons": result, "coverage": coverage,
            "issues": sorted(set(issues)),
            "disclaimer": ("Value equality/difference was inspected only on private ZIP data. "
                           "Pairing requires unique correlation IDs on both sides or "
                           "one exchange without identifiers on either side; it is "
                           "CANDIDATE_ONLY and never proves transformation semantics. "
                           "Unpaired exchanges and missing evidence remain visible. "
                           "No raw payload values or correlation IDs are returned.")}


def compare_for_manifest(raw, aliases):
    """Called only after layered ZIP safety validation in analyze_zip_bytes."""
    return compare_zip_bytes(raw, aliases)
