"""Private, bounded text extraction for LOCAL source-quote validation only.

No attachment or wiki text is sent to the model or written to a manifest.
Optional PDF parser: pypdf, installed by the analyst only after approval.
Extraction is proof that bytes contain text, NOT that a requirement is true.
"""
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from zipfile import ZipFile, BadZipFile

MAX_TEXT = 100000
MAX_PAGES = 12
MAX_DEPTH = 10
MAX_ITEMS = 2500


def _flatten_json(obj):
    values = []
    def walk(value, depth):
        if depth > MAX_DEPTH or len(values) >= MAX_ITEMS:
            return
        if isinstance(value, dict):
            for key, child in list(value.items())[:200]:
                # Keys can help interpret a value, but are not proof of mapping.
                if isinstance(key, str) and len(key) <= 100:
                    values.append(key)
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:200]:
                walk(child, depth + 1)
        elif isinstance(value, str):
            values.append(value[:8000])
        elif value is not None:
            values.append(str(value)[:100])
    walk(obj, 0)
    return " ".join(values)[:MAX_TEXT]


def extract_text(raw, suffix, *, pdf_reader=None):
    """Return (status, bounded locally extracted text, metadata).

    Metadata has no source values. On errors fail closed; never OCR images.
    """
    if not isinstance(raw, bytes) or len(raw) > 8 * 1024 * 1024:
        return "TEXT_UNAVAILABLE", "", {"reason": "SIZE_LIMIT"}
    if suffix == ".json":
        try:
            data = json.loads(raw.decode("utf-8-sig"))
            value = _flatten_json(data)
            return ("LOCAL_TEXT_EXTRACTED" if value.strip() else "TEXT_UNAVAILABLE",
                    value, {"format": "JSON"})
        except (UnicodeDecodeError, ValueError, TypeError):
            return "TEXT_UNAVAILABLE", "", {"reason": "INVALID_JSON"}
    if suffix == ".xml":
        if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.I):
            return "TEXT_UNAVAILABLE", "", {"reason": "XML_ENTITY_FORBIDDEN"}
        try:
            tree = ET.fromstring(raw)
            fragments = []
            for node in tree.iter():
                if len(fragments) >= MAX_ITEMS:
                    break
                if node.text and node.text.strip():
                    fragments.append(node.text.strip()[:8000])
                if node.tail and node.tail.strip():
                    fragments.append(node.tail.strip()[:8000])
            value = " ".join(fragments)[:MAX_TEXT]
            return ("LOCAL_TEXT_EXTRACTED" if value.strip() else "TEXT_UNAVAILABLE",
                    value, {"format": "XML"})
        except ET.ParseError:
            return "TEXT_UNAVAILABLE", "", {"reason": "INVALID_XML"}
    if suffix == ".zip":
        try:
            if not raw.startswith(b"PK\\x03\\x04"):
                return "TEXT_UNAVAILABLE", "", {"reason": "NOT_ZIP"}
            with ZipFile(io.BytesIO(raw)) as archive:
                items = archive.infolist()
                if len(items) > 60:
                    return "TEXT_UNAVAILABLE", "", {"reason": "ZIP_ENTRY_LIMIT"}
                texts = []
                total = 0
                for entry in items:
                    if entry.is_dir():
                        continue
                    name = entry.filename.replace("\\\\", "/")
                    entry_path = PurePosixPath(name)
                    mode = (entry.external_attr >> 16) & 0o170000
                    total += entry.file_size
                    if (name.startswith("/") or ".." in entry_path.parts or ":" in name
                            or entry.flag_bits & 1 or mode == 0o120000 or
                            entry.file_size > 8 * 1024 * 1024 or total > 16 * 1024 * 1024
                            or (entry.compress_size and entry.file_size / entry.compress_size > 100)):
                        return "TEXT_UNAVAILABLE", "", {"reason": "ZIP_UNSAFE"}
                    ext = entry_path.suffix.lower()
                    if ext not in (".json", ".xml"):
                        continue
                    payload = archive.read(entry)
                    substatus, text, _ = extract_text(payload, ext)
                    if substatus == "LOCAL_TEXT_EXTRACTED":
                        texts.append(text)
                    if len(texts) >= 30 or sum(len(t) for t in texts) > MAX_TEXT:
                        return "TEXT_UNAVAILABLE", "", {"reason": "ZIP_TEXT_LIMIT"}
                joined = " ".join(texts)[:MAX_TEXT]
                return ("LOCAL_TEXT_EXTRACTED" if joined.strip() else "TEXT_UNAVAILABLE",
                        joined, {"format": "ZIP", "parsedTextEntries": len(texts)})
        except (BadZipFile, RuntimeError, EOFError, OSError, ValueError):
            return "TEXT_UNAVAILABLE", "", {"reason": "INVALID_ZIP"}
    if suffix == ".pdf":
        if not raw.startswith(b"%PDF-"):
            return "TEXT_UNAVAILABLE", "", {"reason": "INVALID_PDF"}
        if pdf_reader is None:
            try:
                from pypdf import PdfReader
            except ImportError:
                return "PDF_PARSER_NOT_INSTALLED", "", {"reason": "OPTIONAL_PYPDF"}
            pdf_reader = PdfReader
        try:
            doc = pdf_reader(io.BytesIO(raw), strict=True)
            count = len(doc.pages)
            if count > MAX_PAGES:
                return "TEXT_UNAVAILABLE", "", {"reason": "PDF_PAGE_LIMIT"}
            if doc.is_encrypted:
                return "TEXT_UNAVAILABLE", "", {"reason": "PDF_ENCRYPTED"}
            fragments = []
            for page in doc.pages:
                content = page.extract_text() or ""
                fragments.append(content[:MAX_TEXT])
                if sum(len(x) for x in fragments) > MAX_TEXT:
                    return "TEXT_UNAVAILABLE", "", {"reason": "PDF_TEXT_LIMIT"}
            value = " ".join(fragments)[:MAX_TEXT]
            return ("LOCAL_TEXT_EXTRACTED" if value.strip() else "PDF_TEXT_NOT_EXTRACTED",
                    value, {"format": "PDF", "pageCount": count})
        except Exception:
            # Malformed or unsupported PDF is not proof, including OCR-only scans.
            return "PDF_TEXT_NOT_EXTRACTED", "", {"reason": "PDF_PARSE_FAILED"}
    return "TEXT_UNAVAILABLE", "", {"reason": "UNSUPPORTED_FORMAT"}


def text_metadata(text):
    """Privacy-safe exact-document fingerprint without persisting text."""
    return {"textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "textChars": len(text), "storage": "LOCAL_VERIFICATION_ONLY",
            "originConfidence": "LOCAL_BROWSER_SAVE_ORIGIN_NOT_CRYPTOGRAPHICALLY_VERIFIED"}
