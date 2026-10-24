"""Read-only Jira Software active-sprint membership for one configured board.

No arbitrary Sprint customfield parsing and no inference from JQL alone.
If a configured board cannot be verified, the sync fails before replacing data.
"""

import json
import os
from pathlib import Path


def load_board_id(root):
    """Environment overrides the persisted local board configuration.

    The config carries no credentials, but is user-specific and Git-ignored.
    """
    environment = os.environ.get("CCON_JIRA_BOARD_ID")
    if environment is not None:
        return validate_board_id(environment)
    path = Path(root) / ".jira-board.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or "boardId" not in value:
        raise ValueError(".jira-board.json must contain a positive boardId.")
    return validate_board_id(value["boardId"])


def validate_board_id(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError("CCON_JIRA_BOARD_ID must be a positive Jira board number.")
    return int(value)


def fetch_paginated_sprints(client, board):
    sprints, start = [], 0
    while True:
        page = client.get(f"/rest/agile/1.0/board/{board}/sprint",
                          {"state": "active", "startAt": start, "maxResults": 50})
        entries = page.get("values")
        if not isinstance(entries, list) or page.get("startAt", start) != start:
            raise ValueError("Cannot verify active sprint pagination.")
        if not entries and page.get("isLast") is not True:
            raise ValueError("Empty unfinished active-sprint page.")
        sprints.extend(entries)
        total = page.get("total")
        if page.get("isLast") is True:
            break
        if isinstance(total, int) and start + len(entries) >= total:
            break
        if page.get("isLast") is False and not entries:
            raise ValueError("Incomplete active-sprint pagination.")
        if not entries:
            break
        start += len(entries)
        if start > 10000:
            raise ValueError("Unusually large active sprint pagination; refusing incomplete data.")
    return sprints


def fetch_sprint_keys(client, board, sprint_id):
    keys, seen_tokens = set(), set()
    token = None
    while True:
        params = {"maxResults": 100, "fields": "summary"}
        if token:
            params["nextPageToken"] = token
        page = client.get(f"/rest/software/1.0/board/{board}/sprint/{sprint_id}/issue", params)
        issues = page.get("issues")
        if not isinstance(issues, list):
            raise ValueError("Cannot verify sprint issue membership.")
        for issue in issues:
            key = issue.get("key") if isinstance(issue, dict) else None
            if not isinstance(key, str) or not key:
                raise ValueError("Sprint issue without valid key.")
            keys.add(key)
        if page.get("isLast") is True:
            break
        nxt = page.get("nextPageToken")
        if nxt is None and page.get("isLast") is None:
            # No nextPageToken denotes last page for an enhanced endpoint.
            break
        if not nxt or nxt in seen_tokens:
            raise ValueError("Cannot verify complete sprint issue pagination.")
        seen_tokens.add(nxt)
        token = nxt
    return keys


def active_sprint_snapshot(client, board_id):
    board = validate_board_id(board_id)
    if board is None:
        return {"status": "NOT_CONFIGURED", "boardId": None, "sprints": [], "members": {}}
    sprints = fetch_paginated_sprints(client, board)
    membership = {}
    details = []
    seen_ids = set()
    for sprint in sprints:
        sprint_id = sprint.get("id") if isinstance(sprint, dict) else None
        if type(sprint_id) is not int or sprint_id < 1 or sprint_id in seen_ids:
            raise ValueError("Invalid or duplicate active sprint ID.")
        seen_ids.add(sprint_id)
        if sprint.get("state", "active") != "active":
            raise ValueError("Expected active sprint but received a different state.")
        info = {"id": sprint_id, "name": str(sprint.get("name") or ""),
                "startDate": sprint.get("startDate") or "",
                "endDate": sprint.get("endDate") or ""}
        details.append(info)
        for key in fetch_sprint_keys(client, board, sprint_id):
            membership.setdefault(key, []).append({"id": sprint_id, "name": info["name"]})
    return {"status": "VERIFIED", "boardId": board, "sprints": details,
            "members": membership}


def sprint_fields(snapshot, key):
    if snapshot["status"] != "VERIFIED":
        return {"activeSprint": None, "activeSprintStatus": "NOT_CONFIGURED",
                "activeSprintNames": [], "activeSprintIds": []}
    matches = snapshot["members"].get(key, [])
    return {"activeSprint": bool(matches), "activeSprintStatus": "VERIFIED",
            "activeSprintNames": [item["name"] for item in matches],
            "activeSprintIds": [item["id"] for item in matches]}
