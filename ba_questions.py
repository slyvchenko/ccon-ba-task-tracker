"""Persistent human-owned BA questions with source provenance and explicit resolution.

AI can PROPOSE questions but cannot mark them ANSWERED. Disappearance from
missingInfo does NOT mean an answer was found. No Jira/Confluence write API.
"""
import argparse
import hashlib
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from app_config import ROOT, utc_now
from storage import read_json, write_json
from pipeline_lock import pipeline_lock

STATES = {"OPEN", "ANSWERED", "SUPERSEDED", "NOT_APPLICABLE"}
MAX_QUESTIONS = 200
_NO_REVISION = object()


class QuestionConflict(ValueError):
    """Stale manual question edit; never return another analyst's answer."""

    def __init__(self, current_revision):
        super().__init__("Question changed elsewhere. Review the latest saved answer first.")
        self.current_revision = current_revision


def normalize(text):
    return " ".join(text.split()).casefold()


def valid_source_url(value):
    """HTTP(S) source pointer only. Does not verify semantic correctness."""
    if (not isinstance(value, str) or not value or len(value) > 2000 or
            any(char.isspace() or ord(char) < 32 for char in value)):
        return False
    try:
        url = urlparse(value)
        host = url.hostname
        if (url.scheme not in ("http", "https") or not host or
                url.username is not None or url.password is not None or
                (url.port is not None and url.port <= 0)):
            return False
        # urlparse is a splitter, not hostname validation. Accept ordinary
        # ASCII DNS labels and properly formed IPv6 literals, never spaces or
        # encoded-host masquerades from imported legacy question files.
        if ":" in host:
            ipaddress.IPv6Address(host)
            return True
        return (len(host) <= 253 and all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
            for part in host.split(".")))
    except ValueError:
        return False


def question_id(key, text):
    return "Q-" + hashlib.sha256((key + ":" + normalize(text)).encode()).hexdigest()[:14]


def question_file(root, key):
    if not re.fullmatch(r"CCON-\d+", str(key)):
        raise ValueError("Invalid task key.")
    return Path(root) / "data/questions" / (key + ".json")


def question_write_lock(root, key):
    """Per-issue cross-process read-modify-write lock for manual and AI edits.

    Atomic rename keeps JSON well formed, but cannot prevent stale writers from
    overwriting an analyst's answer. All writers of this file share one lock.
    """
    question_file(root, key)  # Validate the key before creating lock paths.
    return pipeline_lock(
        Path(root) / "data/question-locks" / key,
        busy_message="Another question update for this issue is in progress. "
                     "Wait for it to finish, then try again.")


def task_in_scope(root, key):
    context = read_json(Path(root) / "data/jira_context.json", {})
    if context.get("complete") is not True or key not in context.get("issues", {}):
        raise ValueError("Question task must belong to complete personal Jira scope.")


def proposed_questions(analysis=None, evidence=None):
    proposals = []
    analysis = analysis or {}
    for text in analysis.get("missingInfo") or []:
        if isinstance(text, str) and text.strip():
            proposals.append({"text": text.strip(), "origin": "AI_MISSING_INFO"})
    briefing = analysis.get("briefing") or {}
    if isinstance(briefing, dict):
        for text in briefing.get("unknownsUk") or []:
            if isinstance(text, str) and text.strip():
                proposals.append({"text": text.strip(), "origin": "AI_BRIEFING"})
    for artifact in evidence or []:
        for text in artifact.get("questionsUk") or []:
            if isinstance(text, str) and text.strip():
                proposals.append({"text": text.strip(), "origin": "LOG_EVIDENCE"})
    result, seen = [], set()
    for proposal in proposals:
        norm = normalize(proposal["text"])
        if norm and norm not in seen:
            result.append(proposal)
            seen.add(norm)
    return result[:MAX_QUESTIONS]


def read_questions(root, key):
    source = read_json(question_file(root, key), {"key": key, "questions": []})
    if not isinstance(source, dict) or not isinstance(source.get("questions"), list):
        raise ValueError("Invalid local question state.")
    # Historical versions set answerVerified=True on any HTTP(S) URL.
    # Downgrade that unsound claim even before the next write. A link is a
    # source pointer, never machine-confirmed semantic support for an answer.
    for item in source["questions"]:
        if isinstance(item, dict):
            revision = item.get("manualRevision", 0)
            if type(revision) is not int or revision < 0:
                raise ValueError("Invalid local question revision.")
            item["manualRevision"] = revision
            item["answerVerified"] = False
            item["sourceLinkProvided"] = bool(
                item.get("status") == "ANSWERED" and
                valid_source_url(item.get("evidenceUrl")))
    return source


def sync_questions(root, key, analysis=None, evidence=None):
    with question_write_lock(root, key):
        task_in_scope(root, key)
        source = read_questions(root, key)
        prior = {item["id"]: item for item in source["questions"]}
        date = utc_now()
        seen = set()
        for proposal in proposed_questions(analysis, evidence):
            text = proposal["text"][:3000]
            identifier = question_id(key, text)
            seen.add(identifier)
            if identifier in prior:
                prior[identifier]["lastSeenAt"] = date
                # No automatic status change. An answered question stays answered.
            else:
                prior[identifier] = {
                    "id": identifier, "text": text, "status": "OPEN",
                    "origin": proposal["origin"], "firstSeenAt": date,
                    "lastSeenAt": date, "presentInLatestAnalysis": True,
                    "owner": "", "answer": "", "evidenceUrl": "",
                    "manualRevision": 0, "answerVerified": False,
                    "sourceLinkProvided": False, "updatedAt": date,
                }
        for q in prior.values():
            q["presentInLatestAnalysis"] = q["id"] in seen
        source = {"key": key, "updatedAt": date,
                  "questions": sorted(prior.values(), key=lambda q: (q["status"] != "OPEN", q["firstSeenAt"], q["id"]))}
        write_json(question_file(root, key), source, 1 * 1024 * 1024)
        return source


def update_question(root, key, identifier, *, status, owner="", answer="",
                    evidence_url="", expected_manual_revision=_NO_REVISION):
    with question_write_lock(root, key):
        task_in_scope(root, key)
        if status not in STATES:
            raise ValueError("Invalid question state.")
        if expected_manual_revision is not _NO_REVISION and (
                type(expected_manual_revision) is not int or expected_manual_revision < 0):
            raise ValueError("expectedManualRevision must be a nonnegative integer.")
        for name, value, limit in (("owner", owner, 180), ("answer", answer, 8000),
                                   ("evidenceUrl", evidence_url, 2000)):
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(name + " must be bounded text.")
        if evidence_url and not valid_source_url(evidence_url):
            raise ValueError("Evidence must be a valid HTTP(S) URL.")
        if status == "ANSWERED" and not answer.strip():
            raise ValueError("ANSWERED requires a written answer.")
        source = read_questions(root, key)
        match = next((item for item in source["questions"] if item.get("id") == identifier), None)
        if not match:
            raise ValueError("Unknown question ID.")
        current_revision = match["manualRevision"]
        if (expected_manual_revision is not _NO_REVISION and
                expected_manual_revision != current_revision):
            raise QuestionConflict(current_revision)
        # The analyst controls ANSWERED, but neither an HTTP(S) URL nor the
        # answer text verifies its truth. Preserve source-link availability
        # separately; semantic verification requires independent private UAT.
        match.update({"status": status, "owner": owner, "answer": answer,
                      "evidenceUrl": evidence_url, "updatedAt": utc_now(),
                      "sourceLinkProvided": status == "ANSWERED" and bool(evidence_url),
                      "answerVerified": False, "manualRevision": current_revision + 1})
        source["updatedAt"] = utc_now()
        write_json(question_file(root, key), source, 1 * 1024 * 1024)
        return match


def all_evidence(root, key):
    directory = Path(root) / "data/evidence" / key
    if not directory.is_dir():
        return []
    results = []
    for path in sorted(directory.glob("*.json"))[:60]:
        if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
            continue
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("issueKey") == key:
            results.append(payload)
    investigation = Path(root) / "data/investigations" / (key + ".json")
    if investigation.is_file() and not investigation.is_symlink() and investigation.stat().st_size < 4 * 1024 * 1024:
        report = read_json(investigation, {})
        if isinstance(report, dict) and report.get("issueKey") == key:
            results.append({"questionsUk": report.get("questionsUk") or []})
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["sync", "list", "update"])
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--issue", required=True)
    p.add_argument("--id")
    p.add_argument("--status", choices=sorted(STATES))
    p.add_argument("--owner", default="")
    p.add_argument("--answer", default="")
    p.add_argument("--evidence-url", default="")
    args = p.parse_args()
    if args.command == "sync":
        from desk_store import Desk
        task = next((item for item in Desk(args.root).view()["tasks"]
                     if item["key"] == args.issue), None)
        if not task:
            raise ValueError("Issue is not imported.")
        result = sync_questions(args.root, args.issue, task.get("analysis"),
                                all_evidence(args.root, args.issue))
    elif args.command == "list":
        task_in_scope(args.root, args.issue)
        result = read_questions(args.root, args.issue)
    else:
        if not args.id or not args.status:
            raise ValueError("Updating requires --id and --status.")
        result = update_question(args.root, args.issue, args.id, status=args.status,
                                 owner=args.owner, answer=args.answer,
                                 evidence_url=args.evidence_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
