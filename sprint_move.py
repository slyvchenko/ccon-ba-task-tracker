"""Move CCON issues between sprints of the configured board via Jira Agile API.

Usage:
  python sprint_move.py plan.json            # dry run: resolve sprints, show what would change
  python sprint_move.py plan.json --apply    # create missing sprints and move issues

plan.json: {"moves": {"<sprint name>": ["CCON-1", ...], ...}}
Missing sprints are created on the board from .jira-board.json (future state).
Credentials come from load_credentials(); they are never printed or written.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from app_config import ROOT
from jira_sync import JIRA_URL, JiraClient, load_credentials
from sprint_priority import load_board_id

KEY = re.compile(r'^CCON-\d+$')
BATCH = 50  # Agile API limit per move request


class JiraWriteClient(JiraClient):
    def post(self, path, payload):
        if not path.startswith('/rest/agile/1.0/'):
            raise ValueError('Unexpected Jira API path.')
        request = urllib.request.Request(
            JIRA_URL + path, data=json.dumps(payload).encode(), method='POST',
            headers={'Authorization': self.authorization, 'Accept': 'application/json',
                     'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=45) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode('utf-8', 'replace')[:500]
            raise ValueError(f'Jira API returned HTTP {error.code} for {path}: {detail}') from None


def open_sprints(client, board):
    result, start = [], 0
    while True:
        page = client.get(f'/rest/agile/1.0/board/{board}/sprint',
                          {'state': 'active,future', 'startAt': start, 'maxResults': 50})
        values = page.get('values') or []
        result.extend(values)
        if page.get('isLast', True) or not values:
            return result
        start += len(values)


def load_plan(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))['moves']
    plan = {}
    for name, keys in raw.items():
        clean = ' '.join(str(name).split())
        if not clean:
            raise ValueError('Sprint name must not be empty.')
        if clean in plan:
            raise ValueError(f'Sprint "{clean}" is listed twice in the plan.')
        plan[clean] = keys
    seen = {}
    for sprint, keys in plan.items():
        for key in keys:
            if not KEY.match(key):
                raise ValueError(f'Invalid issue key: {key}')
            if key in seen:
                raise ValueError(f'{key} is listed for both "{seen[key]}" and "{sprint}"')
            seen[key] = sprint
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('plan')
    parser.add_argument('--apply', action='store_true', help='Perform changes in Jira.')
    args = parser.parse_args()

    plan = load_plan(args.plan)
    board = load_board_id(ROOT)
    client = JiraWriteClient(*load_credentials(ROOT))
    by_name = {}
    for sprint in open_sprints(client, board):
        by_name.setdefault(' '.join(sprint['name'].split()), []).append(sprint)
    ambiguous = {name: [s['id'] for s in by_name.get(name, [])] for name in plan if len(by_name.get(name, [])) > 1}
    if ambiguous:
        raise ValueError('Ambiguous sprint names (rename in Jira first): ' +
                         '; '.join(f'"{n}" -> ids {ids}' for n, ids in ambiguous.items()))
    sprints = {name: items[0] for name, items in by_name.items()}

    for name, keys in plan.items():
        sprint = sprints.get(name)
        if sprint is None:
            print(f'[{"CREATE" if args.apply else "WOULD CREATE"}] sprint "{name}" on board {board}')
            if args.apply:
                sprint = client.post('/rest/agile/1.0/sprint', {'name': name, 'originBoardId': board})
                sprints[name] = sprint
        else:
            print(f'[FOUND] sprint "{name}" id={sprint["id"]} state={sprint["state"]}')
        print(f'  {"MOVE" if args.apply else "WOULD MOVE"} {len(keys)}: {", ".join(keys)}')
        if args.apply:
            for i in range(0, len(keys), BATCH):
                client.post(f'/rest/agile/1.0/sprint/{sprint["id"]}/issue',
                            {'issues': keys[i:i + BATCH]})
            print('  done')
    if not args.apply:
        print('Dry run only. Re-run with --apply to change Jira.')


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
