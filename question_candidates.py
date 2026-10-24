"""Conservative, read-only candidates for *new* Jira comments.

Matches topic terms and technical identifiers, not semantic truth. Comment text
is shown only in the authorized local BA task UI; candidates never auto-close
questions, fill answers, or modify Jira. Edits to old comments do not become
new replies. An agent may do deeper semantic review separately.
"""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

TECH = re.compile(r"\b(?:[A-Za-z][A-Za-z0-9_]*(?:Code|ID|Ref|Type)|[A-Z][A-Z0-9_]{3,}|CCON-\d+)\b")
WORDS = re.compile(r"[\w.-]{5,}", re.UNICODE)
STOP = {"питання", "потрібно", "відповідь", "підтвердити", "постачальника", "очікуваний",
        "which", "should", "would", "please", "could", "about", "expected", "whether",
        "there", "their", "after", "before", "because", "повинен", "повинна", "буде",
        "також", "цього", "цьому", "задачі", "який", "умови", "коли", "status"}


def timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def terms(value):
    return {w.casefold() for w in WORDS.findall(value or "") if w.casefold() not in STOP}


def question_candidates(question, issue, limit=3):
    if question.get("status") != "OPEN":
        return []
    created = timestamp(question.get("firstSeenAt"))
    if not created:
        return []
    text = str(question.get("text") or "")
    technical = {x.casefold() for x in TECH.findall(text)}
    normal = terms(text)
    candidates = []
    for comment in (issue.get("comments") or [])[:1000]:
        if not isinstance(comment, dict):
            continue
        posted = timestamp(comment.get("created"))
        if not posted or posted <= created:
            continue
        body = comment.get("body") or ""
        if not isinstance(body, str) or len(body) < 16:
            continue
        matched_tech = technical & {x.casefold() for x in TECH.findall(body)}
        matched_words = normal & terms(body)
        # Avoid "every comment is an answer". Require an exact technical
        # identifier in both texts, or two non-generic shared topic words.
        if not matched_tech and len(matched_words) < 2:
            continue
        raw_id = str(comment.get("id") or "")
        if not re.fullmatch(r"\d{1,25}", raw_id):
            continue
        url = str(issue.get("url") or "")
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            continue
        link = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "focusedCommentId=" + raw_id, ""))
        candidates.append({
            "commentId": raw_id, "createdAt": comment.get("created"),
            "sourceUrl": link, "excerpt": body[:500],
            "matchedTerms": sorted(matched_tech or matched_words)[:8],
            "label": "POSSIBLE_RELEVANT_COMMENT_NOT_VERIFIED_ANSWER",
            "score": min(100, len(matched_tech) * 40 + len(matched_words) * 10),
        })
    return sorted(candidates, key=lambda x: (x["score"], x["createdAt"], x["commentId"]), reverse=True)[:limit]


def attach_candidates(questions, issue):
    return [{**q, "answerCandidates": question_candidates(q, issue)} for q in questions]


def questions_with_candidates(root, key):
    from ba_questions import task_in_scope, read_questions
    from storage import read_json
    from pathlib import Path
    task_in_scope(root, key)
    context = read_json(Path(root) / "data/jira_context.json", {})
    issue = context["issues"][key]
    record = read_questions(root, key)
    record["questions"] = attach_candidates(record["questions"], issue)
    return record
