"""Read-only structural analysis of CCON ZIP logs, by REST/errors/selected supplier.

Original payload bytes stay in the authorized local ZIP. Output is an
evidence manifest containing paths, hashes, structural fields, correlation
hints and explicit uncertainty, not wholesale passenger/customer payloads.
"""
import argparse
import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile

from app_config import ROOT, utc_now
from storage import write_json
from supplier_logs import MAX_ZIP, MAX_EXPANDED, supplier_hint

VERSION = 1
MAX_FILES = 10000
MAX_SAMPLE = 3 * 1024 * 1024
MAX_ERRORS = 100
MAX_CASES = 40
MAX_FIELD_PATHS = 120
CORRELATION = re.compile(
    r'(?i)\b(cconFlowId|requestId|traceId|correlationId|conversationId)'
    r'\b[ "=:>]+\s*["\x27]?([A-Za-z0-9._:-]{8,100})')
ERROR_CODE = re.compile(
    r'(?i)\b(?:errorCode|code|faultcode|statusCode|error_type)'
    r'\b[\s"=:>]+\s*["\x27]?([A-Za-z0-9_.:-]{2,90})')
GENERIC_ERROR = re.compile(r'(?i)(?:exception|fault|error|failure|timeout|invalid|reject)')


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def classify(path, aliases):
    """Exactly one provider is selected. Unknown providers are never included."""
    parts = path.parts
    low = [x.casefold() for x in parts]
    accepted = {a.casefold().replace("-", "").replace("_", "") for a in aliases}
    def is_selected(name):
        return name.casefold().replace("-", "").replace("_", "") in accepted
    for i, name in enumerate(low):
        if name in ("supplier", "suppliers", "provider", "providers"):
            if i + 1 < len(parts) and is_selected(parts[i + 1]):
                return "supplier"
            return None
    if any(x in ("errors", "error", "rest-errors", "rest_errors", "exceptions") for x in low[:-1]):
        return "errors"
    if any(x in ("rest", "restlayer", "rest-layer", "rest_api", "rest-api") for x in low[:-1]):
        return "rest"
    # Files may be exported in a flat root folder named "REST-response...".
    base = low[-1]
    if base.startswith(("rest-", "rest_", "rest.")):
        return "rest"
    if base.startswith(("error-", "errors-", "resterror-")):
        return "errors"
    return None


def file_kind(path):
    name = path.name.casefold()
    if re.search(r'(?:request|req|rq)(?:[-_.]|$)', name):
        return "request"
    if re.search(r'(?:response|resp|rs)(?:[-_.]|$)', name):
        return "response"
    return "unknown"


def field_paths(obj, prefix="", limit=MAX_FIELD_PATHS):
    paths = []
    def visit(node, path, depth):
        if len(paths) >= limit or depth > 12:
            return
        if isinstance(node, dict):
            for name, value in list(node.items())[:300]:
                key = (path + "." if path else "") + str(name)[:80]
                paths.append(key)
                visit(value, key, depth + 1)
        elif isinstance(node, list):
            if node:
                visit(node[0], path + "[]", depth + 1)
    visit(obj, prefix, 0)
    return paths[:limit]


def inspect_payload(data, suffix):
    """Extract structural metadata, never persist full payload values."""
    response = {"format": "unknown", "fields": [], "errors": [],
                "correlationHashes": [], "parseWarning": None}
    if len(data) > MAX_SAMPLE:
        response["parseWarning"] = "Large payload: structure was not expanded."
        return response
    text = data.decode("utf-8-sig", errors="replace")
    for match in CORRELATION.finditer(text[:150000]):
        value = match.group(2)
        if len(response["correlationHashes"]) >= 10:
            break
        response["correlationHashes"].append(checksum((match.group(1).lower() + "=" + value).encode())[:16])
    if suffix == ".json" or text.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(text)
            response["format"] = "json"
            response["fields"] = field_paths(parsed)
            def scan(node, depth=0):
                if depth > 8 or len(response["errors"]) >= 20:
                    return
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k.casefold() in ("errorcode", "faultcode", "error_type", "errorcodeid", "error_code"):
                            if isinstance(v, (str, int)):
                                response["errors"].append(str(v)[:90])
                        elif k.casefold() == "code" and isinstance(v, (str, int)) and GENERIC_ERROR.search(text[:5000]):
                            response["errors"].append(str(v)[:90])
                        if isinstance(v, (dict, list)):
                            scan(v, depth + 1)
                elif isinstance(node, list):
                    for x in node[:40]:
                        scan(x, depth + 1)
            scan(parsed)
        except (ValueError, TypeError):
            response["parseWarning"] = "Invalid JSON; retain original ZIP for review."
    elif suffix in (".xml", ".soap") or text.lstrip().startswith("<"):
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            response["parseWarning"] = "DTD/entities are not parsed."
            return response
        try:
            root = ET.fromstring(text)
            response["format"] = "xml"
            paths = []
            def walk(element, prefix="", depth=0):
                if len(paths) >= MAX_FIELD_PATHS or depth > 12:
                    return
                tag = element.tag.split("}")[-1]
                here = (prefix + "/" if prefix else "/") + tag
                paths.append(here[:240])
                for attr in list(element.attrib)[:15]:
                    paths.append((here + "/@" + attr)[:240])
                for child in list(element)[:300]:
                    walk(child, here, depth + 1)
            walk(root)
            response["fields"] = paths[:MAX_FIELD_PATHS]
            for element in root.iter():
                tag = element.tag.split("}")[-1].casefold()
                if tag in ("errorcode", "faultcode", "error_code"):
                    if element.text:
                        response["errors"].append(element.text.strip()[:90])
                elif tag in ("error", "fault", "providererror"):
                    code = element.get("Code") or element.get("code")
                    if code:
                        response["errors"].append(code[:90])
                if len(response["errors"]) >= 20:
                    break
        except ET.ParseError:
            response["parseWarning"] = "Invalid XML; retain original ZIP for review."
    elif suffix in (".txt", ".log"):
        response["format"] = "text"
    if not response["errors"] and GENERIC_ERROR.search(text[:30000]):
        response["errors"] = [x.group(1) for x in ERROR_CODE.finditer(text[:30000])][:20]
    response["errors"] = sorted(set(response["errors"]))[:20]
    response["correlationHashes"] = sorted(set(response["correlationHashes"]))
    return response


def analyze_zip_bytes(raw, supplier, source_name="download.zip"):
    """One ZIP may contain many suppliers; only the task's supplier is examined."""
    if not isinstance(supplier, dict) or not supplier.get("aliases"):
        raise ValueError("Supplier identity must be verified before ZIP inspection.")
    if len(raw) > MAX_ZIP:
        raise ValueError("ZIP over 100 MB.")
    samples = []
    counts = Counter()
    errors = Counter()
    warnings = []
    ignored = 0
    total = 0
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            info = archive.infolist()
            if len(info) > MAX_FILES or sum(i.file_size for i in info) > MAX_EXPANDED:
                raise ValueError("ZIP entry count or expansion size exceeds limit.")
            for entry in info:
                if entry.is_dir():
                    continue
                name = entry.filename.replace("\\", "/")
                path = PurePosixPath(name)
                if (path.is_absolute() or ".." in path.parts or
                        any(":" in part for part in path.parts) or "\x00" in name):
                    raise ValueError("Unsafe ZIP member name.")
                layer = classify(path, supplier["aliases"])
                if not layer:
                    ignored += 1
                    continue
                if path.suffix.casefold() not in (".xml", ".soap", ".json", ".log", ".txt"):
                    continue
                counts[layer] += 1
                total += 1
                # Process every matching file for counts, errors and fields;
                # retain detailed examples only up to the documented cap.
                if entry.file_size > MAX_SAMPLE:
                    info_payload = {"format": "unread_large", "fields": [], "errors": [],
                                    "correlationHashes": [], "parseWarning": "Individual payload >3MB."}
                    raw_data = None
                else:
                    raw_data = archive.read(entry)
                    info_payload = inspect_payload(raw_data, path.suffix.casefold())
                errors.update(info_payload["errors"])
                if info_payload["parseWarning"]:
                    warnings.append({"layer": layer, "file": path.name[:150],
                                     "reason": info_payload["parseWarning"]})
                if len(samples) < MAX_CASES:
                    samples.append({
                        "id": len(samples) + 1, "layer": layer,
                        "file": str(path)[:300],
                        "kind": file_kind(path),
                        "size": entry.file_size,
                        "sha256": checksum(raw_data) if raw_data is not None else None,
                        **info_payload,
                    })
    except (BadZipFile, RuntimeError, NotImplementedError):
        raise ValueError("Invalid or encrypted ZIP.") from None
    if not counts["rest"] and not counts["supplier"] and not counts["errors"]:
        raise ValueError("ZIP has no selected supplier, REST or errors layer.")
    if not counts["supplier"]:
        warnings.append({"reason": "No selected supplier payloads; do not infer supplier behavior."})
    if not counts["rest"]:
        warnings.append({"reason": "No REST payloads; REST-to-supplier comparison is blocked."})
    if total > MAX_CASES:
        warnings.append({"reason": f"{total - MAX_CASES} additional files counted but not retained as detailed examples; split by flow for full case-level coverage."})
    # Never treat coincidentally identical sequence numbers as proof of mapping.
    matches = []
    for i, left in enumerate(samples):
        if left["layer"] != "rest" or not left["correlationHashes"]:
            continue
        candidates = [right for right in samples if right["layer"] == "supplier"
                      and set(left["correlationHashes"]) & set(right["correlationHashes"])]
        if len(candidates) == 1:
            right = candidates[0]
            matches.append({"restSample": left["id"], "supplierSample": right["id"],
                            "basis": "shared explicit correlation ID hash", "confidence": "CANDIDATE_ONLY"})
    questions = []
    if not counts["rest"] or not counts["supplier"]:
        questions.append("Потрібні REST і supplier request/response для перевірки трансформації даних.")
    if not matches and counts["rest"] and counts["supplier"]:
        questions.append("Яке поле correlation/flow або часовий порядок однозначно пов'язує REST і supplier обміни?")
    if counts["errors"]:
        questions.append("Які error codes зіставляються із конкретними REST-відповідями та supplier-викликами?")
    if any(item["kind"] == "unknown" for item in samples):
        questions.append("Як визначати напрямок request/response для файлів без відповідного позначення?")
    return {
        "schemaVersion": VERSION, "source": source_name[:200],
        "sourceSha256": checksum(raw), "supplier": supplier["name"],
        "counts": dict(counts), "totalMatchingFiles": total,
        "ignoredOtherSupplierAndUnrelatedFiles": ignored,
        "errorCodes": [{"code": k, "count": v} for k, v in errors.most_common(MAX_ERRORS)],
        "samples": samples,
        "correlationCandidates": matches,
        "questionsUk": questions,
        "warnings": warnings[:100],
        "status": "PARTIAL" if questions or warnings else "STRUCTURE_ANALYZED",
        "interpretation": (
            "REST request -> CCON translation -> supplier request; "
            "supplier response -> CCON interpretation -> REST response. "
            "Structural/correlation candidates are NOT verified value mapping or root cause."
        ),
    }


def analyze_zip(path, supplier_name, root=ROOT, issue_key=None, flow_id=None):
    supplier = supplier_hint(supplier_name)
    if not supplier:
        raise ValueError("Supplier must be explicitly identifiable from issue context/title.")
    source = Path(path)
    if source.stat().st_size > MAX_ZIP:
        raise ValueError("ZIP over 100 MB.")
    result = analyze_zip_bytes(source.read_bytes(), supplier, source.name)
    if issue_key is not None:
        if not re.fullmatch(r"CCON-\d+", issue_key):
            raise ValueError("Invalid Jira issue key.")
        if flow_id is not None and not re.fullmatch(
                r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", flow_id):
            raise ValueError("Invalid flow ID.")
        directory = Path(root) / "data/evidence" / issue_key
        filename = (flow_id.lower() if flow_id else result["sourceSha256"][:20]) + ".json"
        result["issueKey"] = issue_key
        result["flowId"] = flow_id
        result["createdAt"] = utc_now()
        write_json(directory / filename, result, 4 * 1024 * 1024)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--supplier", required=True, help="Exact supplier name or recognized Jira prefix, e.g. AF/KL")
    parser.add_argument("--issue", help="CCON-123")
    parser.add_argument("--flow-id")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    report = analyze_zip(args.zip, args.supplier, args.root, args.issue, args.flow_id)
    print(json.dumps({k: v for k, v in report.items() if k != "samples"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
