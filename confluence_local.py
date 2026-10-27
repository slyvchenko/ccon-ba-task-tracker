"""Read-only Confluence page handoff. No cookies, remote API or background browser.

Only full canonical page URLs explicitly referenced by the current Jira issue
are eligible. Local HTML remains private; manifest stores hashes/counts only.
"""
import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from app_config import ROOT, utc_now
from jira_attachments import _metadata
from storage import read_json, write_json

MAX_HTML = 4 * 1024 * 1024
MAX_TEXT = 100000
MAX_LINKS = 40
PAGE = re.compile(r"/wiki/spaces/[A-Za-z0-9_-]{1,100}/pages/(?P<id>\d{1,20})(?:/[^?#]*)?\Z")
URLS = re.compile(r"https://aerticket\.atlassian\.net/wiki/[^\s<>\"'\]]+", re.I)


def page_ref(url):
    if not isinstance(url, str) or len(url) > 2000:
        return None
    try:
        p = urlsplit(url)
        if p.scheme != "https" or p.netloc != "aerticket.atlassian.net" or p.query or p.fragment:
            return None
        match = PAGE.fullmatch(p.path)
        if match:
            return match.group("id"), "https://aerticket.atlassian.net" + p.path.rstrip("/")
    except ValueError:
        return None
    return None


def linked_pages(issue):
    found = {}
    def walk(node, depth=0):
        if depth > 12 or len(found) >= MAX_LINKS:
            return
        if isinstance(node, str):
            for url in URLS.findall(node[:30000]):
                reference = page_ref(url.rstrip(".,;)"))
                if reference:
                    found.setdefault(reference[0], reference[1])
        elif isinstance(node, dict):
            for name, value in list(node.items())[:200]:
                if name in ("description", "descriptionAdf", "comments", "content", "attrs",
                            "href", "url", "marks", "text", "body", "bodyAdf"):
                    walk(value, depth+1)
        elif isinstance(node, list):
            for value in node[:250]:
                walk(value, depth+1)
    for field in ("description", "descriptionAdf", "comments"):
        walk(issue.get(field))
    return found


def page_path(root, key, page_id):
    if not re.fullmatch(r"CCON-\d+", str(key)) or not re.fullmatch(r"\d{1,20}", str(page_id)):
        raise ValueError("Invalid page identity.")
    return Path(root) / "downloads/wiki" / key / (str(page_id) + ".html")


class Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocked = 0
        self.tokens = []
        self.chars = 0
        self.form_depth = 0
        self.password_form = False
    def handle_starttag(self, tag, attrs):
        if tag == "form":
            self.form_depth += 1
        elif tag == "input" and self.form_depth:
            self.password_form |= any(
                key == "type" and isinstance(value, str) and value.lower() == "password"
                for key, value in attrs)
        if tag in ("script", "style", "head", "svg"):
            self.blocked += 1
        if tag in ("p", "div", "br", "li", "td", "tr", "h1", "h2", "h3"):
            self.tokens.append(" ")
    def handle_endtag(self, tag):
        if tag == "form" and self.form_depth:
            self.form_depth -= 1
        if tag in ("script", "style", "head", "svg") and self.blocked:
            self.blocked -= 1
        if tag in ("p", "div", "li", "td", "tr"):
            self.tokens.append(" ")
    def handle_data(self, data):
        if not self.blocked and self.chars < MAX_TEXT:
            portion = data[:MAX_TEXT - self.chars]
            self.tokens.append(portion)
            self.chars += len(portion)


def extract_html(raw):
    if len(raw) > MAX_HTML:
        raise ValueError("WIKI_HTML_TOO_LARGE")
    decoded = raw.decode("utf-8-sig")
    if not re.search(r"(?is)<html\b|<!doctype\s+html\b", decoded[:5000]):
        raise ValueError("WIKI_NOT_HTML")
    parser = Extractor()
    parser.feed(decoded)
    text = " ".join(" ".join(parser.tokens).split())[:MAX_TEXT]
    if not text:
        raise ValueError("WIKI_EMPTY_TEXT")
    # Only a password input inside a real form is an authentication signal.
    # HTMLParser ignores literal markup in scripts and HTML comments.
    if parser.password_form:
        raise ValueError("WIKI_SIGN_IN")
    if re.search(r"(?i)^(?:sign in|log in|you need to log in)", text[:100]):
        raise ValueError("WIKI_SIGN_IN")
    return text


def prepare(root=ROOT, key=None):
    root = Path(root)
    issue = _metadata(root, key)
    jobs = [{"pageId": pid, "issueKey": key, "url": url,
             "contextFingerprint": issue["fingerprint"],
             "saveAs": str(page_path(root, key, pid)),
             "state": "AUTHENTICATED_BROWSER_DOWNLOAD_REQUIRED"}
            for pid, url in sorted(linked_pages(issue).items())]
    report = {"jobs": jobs, "readOnlyBrowser": True, "generatedAt": utc_now(),
              "state": "BROWSER_ACTIONS_PENDING"}
    write_json(root / "data/wiki_handoff" / (key + ".json"), report, 256000)
    return report


def process(root=ROOT, key=None):
    root = Path(root)
    issue = _metadata(root, key)
    plan = read_json(root / "data/wiki_handoff" / (key + ".json"), {})
    rows = []
    references = linked_pages(issue)
    jobs = plan.get("jobs") if isinstance(plan, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("Run confluence_local.py prepare first.")
    for job in jobs[:MAX_LINKS]:
        if not isinstance(job, dict):
            continue
        ident = job.get("pageId")
        if (job.get("issueKey") != key or ident not in references
                or references[ident] != job.get("url")
                or job.get("contextFingerprint") != issue["fingerprint"]):
            rows.append({"pageId": ident, "status": "STALE"})
            continue
        source = page_path(root, key, ident)
        if not source.is_file() or source.is_symlink():
            rows.append({"pageId": ident, "status": "PENDING"})
            continue
        try:
            if source.stat().st_size > MAX_HTML:
                raise ValueError("WIKI_HTML_TOO_LARGE")
            raw = source.read_bytes()
            page_text = extract_html(raw)
            manifest = {"issueKey": key, "pageId": ident, "url": references[ident],
                        "contextFingerprint": issue["fingerprint"],
                        "sourceSha256": hashlib.sha256(raw).hexdigest(),
                        "textSha256": hashlib.sha256(page_text.encode()).hexdigest(),
                        "textChars": len(page_text),
                        "status": "LOCAL_TEXT_EXTRACTED", "inspectedAt": utc_now(),
                        "limitation": "TEXT_OCCURRENCE_NOT_REQUIREMENT_TRUTH"}
            write_json(root / "data/wiki_evidence" / key / (ident + ".json"), manifest, 32000)
            rows.append({"pageId": ident, "status": "LOCAL_TEXT_EXTRACTED"})
        except (ValueError, UnicodeError, OSError):
            rows.append({"pageId": ident, "status": "FAILED"})
    return {"results": rows}


def current_sources(root, key, issue):
    """Return local-only source text map; recheck fingerprints and bytes."""
    sources, metadata = {}, []
    for ident, url in list(linked_pages(issue).items())[:MAX_LINKS]:
        try:
            record = read_json(Path(root) / "data/wiki_evidence" / key / (ident + ".json"), {})
        except (ValueError, OSError):
            continue
        if (not isinstance(record, dict) or record.get("issueKey") != key
                or record.get("pageId") != ident or record.get("url") != url
                or record.get("contextFingerprint") != issue.get("fingerprint")
                or record.get("status") != "LOCAL_TEXT_EXTRACTED"):
            continue
        source = page_path(root, key, ident)
        if not source.is_file() or source.is_symlink() or source.stat().st_size > MAX_HTML:
            continue
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != record.get("sourceSha256"):
            continue
        try:
            data = extract_html(raw)
        except (UnicodeError, ValueError):
            continue
        if hashlib.sha256(data.encode()).hexdigest() != record.get("textSha256"):
            continue
        sources[url] = data
        metadata.append({"pageId": ident, "status": "LOCAL_TEXT_VERIFIED",
                         "sourceSha256": record["sourceSha256"],
                         "limitation": "SOURCE_TEXT_PRESENT_NOT_FACT_PROVEN"})
    return sources, metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "process"))
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--issue", required=True)
    args = p.parse_args()
    result = prepare(args.root, args.issue) if args.action == "prepare" else process(args.root, args.issue)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
