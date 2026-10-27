"""Local Codex/Work evidence discovery plan for Jira-linked Kibana searches.

This does NOT impersonate an authenticated browser. The local agent opens
approved Jira/Kibana links in the user's existing logged-in browser and
records exported ZIPs with layered_evidence.py. No token/cookie capture.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from app_config import ROOT, utc_now
from storage import read_json, write_json
from supplier_logs import links_in, flow_references, supplier_hint

MAX_KIBANA_LINKS = 80
MAX_ERROR_CASES = 30
# An arbitrary Jira link whose hostname happens to contain "kibana" is not
# authorization to open that external origin in the analyst's browser.
BUILTIN_KIBANA_ORIGINS = {"http://192.168.197.246:5601"}
ALLOWED_ORIGINS_ENV = "CCON_KIBANA_ALLOWED_ORIGINS"


def _origin(raw, *, configuration=False):
    """Canonical exact scheme/hostname/port; reject credentials and bad ports."""
    if not isinstance(raw, str) or len(raw) > 8000:
        return None
    try:
        parsed = urlparse(raw.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        port = parsed.port  # Reject nonnumeric and out-of-range ports.
        if port == 0:
            return None
        if configuration and (parsed.path not in ("", "/") or
                              parsed.params or parsed.query or parsed.fragment):
            return None
        return "{}://{}:{}".format(
            parsed.scheme, parsed.hostname.lower(),
            port if port is not None else (443 if parsed.scheme == "https" else 80))
    except ValueError:
        return None


def approved_kibana_origins():
    origins = set(BUILTIN_KIBANA_ORIGINS)
    # Opt-in local configuration, never from Jira, URLs, AI, or supplier logs.
    # Bare hostnames and wildcards are intentionally not accepted.
    for configured in os.environ.get(ALLOWED_ORIGINS_ENV, "").split(",")[:20]:
        origin = _origin(configured, configuration=True)
        if origin:
            origins.add(origin)
    return origins


# Opening an arbitrary GET endpoint on a trusted Kibana host is not a
# read-only Discover action. Allow only known analyst UI entry points.
KIBANA_VIEW_PATHS = frozenset({"/app/kibana", "/app/discover"})


def _is_discover_view(raw):
    try:
        parsed = urlparse(raw)
        path = parsed.path.rstrip("/")
        if path == "/app/discover":
            return True
        if path == "/app/kibana":
            # The legacy route lives in the fragment, not the pathname.
            # /app/kibana#/dev_tools/console is NOT read-only Discover.
            fragment = unquote(parsed.fragment).lower()
            return fragment == "/discover" or fragment.startswith(("/discover/", "/discover?"))
        return False
    except ValueError:
        return False


def discover_links(issue):
    found = {}
    allowed = approved_kibana_origins()
    values = {"description": issue.get("descriptionAdf") or issue.get("description"),
              "comments": issue.get("comments") or []}
    for url in links_in(values):
        url = url.strip().strip(".,);")
        if _origin(url) not in allowed or not _is_discover_view(url):
            continue
        label = "ERROR_SEARCH" if any(x in unquote(url).lower()
                   for x in ("errorlog", "error_log", "exception", "errorlevel", "error level", "errors")) else "SEARCH"
        # URLs may carry auth-sensitive search parameters. They are local-only,
        # never sent to model prompts or committed to public GitHub.
        found.setdefault(url, label)
        if len(found) >= MAX_KIBANA_LINKS:
            break
    return [{"url": url, "kind": label} for url, label in found.items()]


def plan_for_issue(issue, count=MAX_ERROR_CASES):
    if type(count) is not int or not 1 <= count <= MAX_ERROR_CASES:
        raise ValueError("Maximum 30 examples per error search.")
    supplier = supplier_hint(issue.get("summary") or "")
    links = discover_links(issue)
    flows = flow_references(issue)
    actions = []
    for item in links:
        actions.append({
            "kind": item["kind"],
            "url": item["url"],
            "readOnly": True,
            "maxCases": count if item["kind"] == "ERROR_SEARCH" else 1,
            "instructionUk": ("Переглянути доступні приклади помилки, згрупувати за "
                              "code/method/correlation, відібрати до 30 різних обмінів; "
                              "для кожного завантажити авторизований ZIP, якщо доступний."
                              if item["kind"] == "ERROR_SEARCH" else
                              "Відкрити пошук Kibana у чинній браузерній сесії; "
                              "перевірити timestamps та flow IDs і завантажити ZIP."),
        })
    if flows and not links:
        actions.append({"kind": "FLOW_DOWNLOAD_ONLY", "readOnly": True, "maxCases": 1,
                        "instructionUk": "Ідентифікатор cconFlowId є, але Kibana URL недоступний."})
    gaps = []
    if not supplier:
        gaps.append("Не визначено постачальника. Уточнити за issue/коментарями, не змішувати supplier-папки.")
    if not links and not flows:
        gaps.append("У Jira не знайдено Kibana посилань/cconFlowId. Запросити приклад або пошукові параметри.")
    return {"key": issue.get("key"), "supplier": supplier, "kibana": actions,
            "flows": flows, "questionsUk": gaps,
            "maxExamplesPerErrorSearch": count}


def create_plan(root=ROOT, issue_key=None, error_cases=MAX_ERROR_CASES):
    root = Path(root)
    context = read_json(root / "data/jira_context.json", {})
    if context.get("complete") is not True:
        raise ValueError("Complete Jira sync required before Kibana discovery.")
    issues = context.get("issues", {})
    if issue_key:
        if issue_key not in issues:
            raise ValueError("Issue not in personal Jira scope.")
        issues = {issue_key: issues[issue_key]}
    plan = {"createdAt": utc_now(), "status": "LOCAL_BROWSER_ACTIONS_REQUIRED",
            "readOnly": True,
            "tasks": [plan_for_issue(issue, error_cases) for issue in issues.values()]}
    write_json(root / "data/kibana_evidence_plan.json", plan, 3 * 1024 * 1024)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--issue", help="Optional CCON issue")
    parser.add_argument("--max-errors", type=int, default=30)
    args = parser.parse_args()
    result = create_plan(args.root, args.issue, args.max_errors)
    print(json.dumps({"tasks": len(result["tasks"]),
                      "links": sum(len(t["kibana"]) for t in result["tasks"]),
                      "questions": sum(len(t["questionsUk"]) for t in result["tasks"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
