"""Read-only Jira import for CCON BA Desk (Python standard library only).

The inbox receives a compact complete snapshot. Full Jira source material stays
in data/jira_context.json. Credentials never enter either output.
"""
import argparse
import base64
import copy
import ctypes
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from pipeline_lock import pipeline_lock, replace_file

ROOT = Path(__file__).resolve().parent
JIRA_URL = 'https://aerticket.atlassian.net'
JQL = ('project = CCON AND status != Done AND assignee = currentUser() '
       'AND (labels IS EMPTY OR labels NOT IN ("blocked")) AND issuetype != Epic '
       'ORDER BY priority DESC, updated DESC')
FIELDS = ('summary,status,priority,updated,description,issuetype,reporter,'
          'assignee,issuelinks,labels,created,attachment,resolution,parent')
SNAPSHOT_LIMIT = 5 * 1024 * 1024
MANUAL_FIELDS = {'manualStatus', 'note', 'active', 'importedAt', 'modifiedAt'}


def now():
    return datetime.now(timezone.utc).isoformat()


def unprotect_token(encoded):
    """Decode a base64 CurrentUser CryptProtectData blob on Windows."""
    if os.name != 'nt':
        raise ValueError('Windows DPAPI credentials require Windows; use environment variables here.')
    try:
        encrypted = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError('Invalid encrypted Jira token.') from None
    if not encrypted:
        raise ValueError('Empty encrypted Jira token.')

    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    storage = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
    source = Blob(len(encrypted), storage)
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_uint32, ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    # CRYPTPROTECT_UI_FORBIDDEN: never prompt from a scheduled import.
    if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                    1, ctypes.byref(target)):
        raise ValueError('Cannot decrypt Jira token for this Windows user.')
    try:
        return ctypes.string_at(target.data, target.size).decode('utf-8')
    finally:
        if target.data:
            ctypes.memset(target.data, 0, target.size)
            kernel.LocalFree(target.data)


def load_credentials(root):
    email, token = os.environ.get('JIRA_EMAIL'), os.environ.get('JIRA_API_TOKEN')
    if email or token:
        if not email or not token:
            raise ValueError('Set both JIRA_EMAIL and JIRA_API_TOKEN.')
        return email, token
    path = Path(root) / '.jira-credentials.json'
    try:
        credentials = json.loads(path.read_text(encoding='utf-8-sig'))
        email = credentials['email']
        token = unprotect_token(credentials['tokenDpapi'])
    except OSError:
        raise ValueError('Jira credentials are not configured. See README.md.') from None
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('Invalid .jira-credentials.json; expected email and tokenDpapi.') from None
    if not isinstance(email, str) or not email.strip() or not isinstance(token, str) or not token:
        raise ValueError('Jira credentials are incomplete.')
    return email, token


class JiraClient:
    def __init__(self, email, token):
        self.authorization = 'Basic ' + base64.b64encode((email + ':' + token).encode()).decode()
        self.opener = urllib.request.build_opener()

    def get(self, path, params=None):
        if not path.startswith('/rest/api/3/'):
            raise ValueError('Unexpected Jira API path.')
        url = JIRA_URL + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={
            'Authorization': self.authorization, 'Accept': 'application/json'})
        for attempt in range(4):
            try:
                with self.opener.open(request, timeout=45) as response:
                    result = json.load(response)
                if not isinstance(result, dict):
                    raise ValueError('Unexpected Jira API response.')
                return result
            except urllib.error.HTTPError as error:
                if error.code in (429, 502, 503, 504) and attempt < 3:
                    try:
                        delay = float(error.headers.get('Retry-After', 2 ** attempt))
                    except (TypeError, ValueError):
                        delay = 2 ** attempt
                    time.sleep(max(0, min(delay, 30)))
                    continue
                raise ValueError('Jira API returned HTTP ' + str(error.code) +
                                 '; no snapshot was imported.') from None
            except (urllib.error.URLError, TimeoutError):
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise ValueError('Jira connection failed; no snapshot was imported.') from None


def adf_text(value):
    """Readable ADF text, retaining paragraphs, list items, mentions and tables."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ''.join(adf_text(item) for item in value)
    if not isinstance(value, dict):
        return ''
    kind, attrs = value.get('type'), value.get('attrs') or {}
    if kind == 'text':
        return value.get('text', '')
    if kind == 'hardBreak':
        return '\n'
    if kind == 'mention':
        return attrs.get('text') or '[згадка: ' + str(attrs.get('id', '')) + ']'
    if kind in ('inlineCard', 'blockCard'):
        return str(attrs.get('url', '')) + ('\n' if kind == 'blockCard' else '')
    if kind in ('media', 'mediaSingle') and not value.get('content'):
        return '[вкладення: ' + str(attrs.get('alt') or attrs.get('id') or 'файл') + ']'
    text = adf_text(value.get('content', []))
    if kind == 'listItem':
        return '- ' + text.strip() + '\n'
    if kind in ('paragraph', 'heading', 'codeBlock', 'blockquote', 'tableRow', 'rule'):
        return text + '\n'
    if kind in ('tableCell', 'tableHeader'):
        return text.strip() + '\t'
    return text


def person(value, include_email=False):
    value = value or {}
    result = {key: value[key] for key in ('accountId', 'displayName') if value.get(key)}
    if include_email and value.get('emailAddress'):
        result['emailAddress'] = value['emailAddress']
    return result


def fetch_issues(client):
    issues, tokens = {}, set()
    next_token = None
    while True:
        params = {'jql': JQL, 'maxResults': 100, 'fields': FIELDS}
        if next_token:
            params['nextPageToken'] = next_token
        page = client.get('/rest/api/3/search/jql', params)
        if not isinstance(page.get('issues'), list):
            raise ValueError('Jira search did not return issues; import cancelled.')
        for issue in page['issues']:
            key = issue.get('key', '')
            if not re.fullmatch(r'CCON-\d+', key) or not isinstance(issue.get('fields'), dict):
                raise ValueError('Invalid CCON search result; import cancelled.')
            if key in issues:
                raise ValueError('Duplicate issue across Jira pages; import cancelled.')
            issues[key] = issue
        if page.get('isLast') is True:
            return issues
        next_token = page.get('nextPageToken')
        if not next_token or next_token in tokens:
            raise ValueError('Cannot confirm complete Jira pagination; import cancelled.')
        tokens.add(next_token)


def fetch_comments(client, key):
    result, ids = [], set()
    start = 0
    while True:
        page = client.get('/rest/api/3/issue/' + urllib.parse.quote(key, safe='') + '/comment',
                          {'startAt': start, 'maxResults': 100, 'orderBy': 'created'})
        comments, total = page.get('comments'), page.get('total')
        if not isinstance(comments, list) or not isinstance(total, int) or total < 0:
            raise ValueError('Incomplete comments for ' + key + '; import cancelled.')
        if page.get('startAt', start) != start:
            raise ValueError('Unexpected comment page for ' + key + '; import cancelled.')
        for comment in comments:
            identity = str(comment.get('id', ''))
            if not identity or identity in ids:
                raise ValueError('Duplicate or missing comment id for ' + key + '; import cancelled.')
            ids.add(identity)
            result.append({'id': identity, 'body': adf_text(comment.get('body')).strip(),
                           'bodyAdf': comment.get('body'), 'created': comment.get('created', ''),
                           'updated': comment.get('updated', ''),
                           'author': person(comment.get('author'))})
        start += len(comments)
        if start == total:
            return result
        if start > total or not comments:
            raise ValueError('Cannot confirm all comments for ' + key + '; import cancelled.')


def normalize_issue(issue, comments, stamp):
    key, fields = issue['key'], issue['fields']
    links, blocked_by, blocks = [], [], []
    for link in fields.get('issuelinks') or []:
        relation = link.get('type') or {}
        for direction in ('inward', 'outward'):
            other = link.get(direction + 'Issue')
            if not isinstance(other, dict) or not other.get('key'):
                continue
            other_fields = other.get('fields') or {}
            label = relation.get(direction, relation.get('name', ''))
            status = other_fields.get('status') or {}
            closed = ((status.get('statusCategory') or {}).get('key') == 'done')
            links.append({'id': str(link.get('id', '')), 'type': relation.get('name', ''),
                          'direction': direction, 'relationship': label, 'linkedKey': other['key'],
                          'summary': other_fields.get('summary', ''), 'jiraStatus': status.get('name', ''),
                          'resolved': closed})
            if relation.get('name', '').lower() == 'blocks' and not closed:
                (blocked_by if direction == 'inward' else blocks).append(other['key'])
    context = {'key': key, 'summary': fields.get('summary', ''), 'url': JIRA_URL + '/browse/' + key,
               'jiraStatus': (fields.get('status') or {}).get('name', ''),
               'statusCategory': ((fields.get('status') or {}).get('statusCategory') or {}).get('key', ''),
               'priority': (fields.get('priority') or {}).get('name', ''),
               'issueType': (fields.get('issuetype') or {}).get('name', ''),
               'jiraUpdatedAt': fields.get('updated', ''), 'createdAt': fields.get('created', ''),
               'description': adf_text(fields.get('description')).strip(),
               'descriptionAdf': fields.get('description'), 'comments': comments,
               'reporter': person(fields.get('reporter'), include_email=True),
               'assignee': person(fields.get('assignee')), 'labels': fields.get('labels') or [],
               'resolution': (fields.get('resolution') or {}).get('name', ''),
               'parentKey': (fields.get('parent') or {}).get('key', ''),
               'attachments': [{k: item[k] for k in ('id', 'filename', 'mimeType', 'size', 'created', 'content')
                                if k in item} for item in (fields.get('attachment') or [])],
               'links': links, 'blockedBy': blocked_by, 'blocks': blocks, 'retrievedAt': stamp}
    if not isinstance(context['summary'], str) or not context['summary'].strip():
        raise ValueError('Issue ' + key + ' has no summary; import cancelled.')
    return context


def fingerprint(context, all_contexts):
    own = {k: v for k, v in context.items() if k not in ('retrievedAt', 'fingerprint')}
    dependencies = {}
    for link in context['links']:
        linked = all_contexts.get(link['linkedKey'])
        if linked:
            dependencies[link['linkedKey']] = {k: v for k, v in linked.items()
                                              if k not in ('retrievedAt', 'fingerprint')}
    raw = json.dumps({'issue': own, 'immediateLinkedIssues': dependencies}, ensure_ascii=False,
                     sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def read_existing(root):
    existing = {}
    inbox = Path(root) / 'inbox' / 'CCON_BA_Snapshot.json'
    if inbox.exists():
        try:
            existing = {task['key']: task for task in json.loads(inbox.read_text(encoding='utf-8-sig'))['tasks']}
        except (ValueError, KeyError, TypeError):
            raise ValueError('Existing inbox snapshot is invalid; preserve it and repair before syncing.') from None
    database = Path(root) / 'ba_state.db'
    if database.exists():
        # The DB is the authoritative source for the last imported analysis.
        connection = sqlite3.connect(str(database))
        try:
            for key, raw in connection.execute('SELECT key,snapshot FROM tasks'):
                existing[key] = json.loads(raw)
        finally:
            connection.close()
    return existing


def make_task(context, prior):
    task = {key: copy.deepcopy(value) for key, value in prior.items() if key not in MANUAL_FIELDS}
    same = prior.get('contextFingerprint') == context['fingerprint']
    has_analysis = bool(prior.get('analysis')) or prior.get('aiStatus') not in (None, '', 'NOT ANALYZED')
    task.update({key: context[key] for key in ('key', 'summary', 'url', 'jiraStatus', 'priority', 'jiraUpdatedAt')})
    task.update(contextFingerprint=context['fingerprint'], contextRetrievedAt=context['retrievedAt'],
                contextAvailable=True)
    if same and has_analysis:
        return task
    reason = ('Дані Jira або пов’язаних задач змінилися після попереднього аналізу. '
              'Потрібно перевірити опис, усі коментарі та залежності.' if has_analysis else
              'Повний опис і доступні коментарі отримано з Jira. Поглиблений аналіз ще не виконано.')
    # Preserve old material for inspection, but do not present it as current advice.
    if has_analysis:
        analysis = task.get('analysis')
        if not isinstance(analysis, dict):
            analysis = {'previousStatus': prior.get('aiStatus', ''),
                        'previousReason': prior.get('statusReason', ''),
                        'previousNextAction': prior.get('nextAction', ''),
                        'previousReadyOutput': prior.get('readyOutput', '')}
        analysis['stale'] = True
        analysis['staleReason'] = reason
        task['analysis'] = analysis
    else:
        task.pop('analysis', None)
    task.update(aiStatus='NOT ANALYZED', waitingOn='NOT FOUND', blocking=bool(context['blocks']),
                statusReason=reason, nextAction='Переглянути повний контекст Jira й визначити наступну дію BA.',
                readyOutput='', analysisSource='Jira API — повний контекст; очікує аналізу.')
    return task


def atomic_json(path, document, limit=None):
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')
    if limit is not None and len(raw) > limit:
        raise ValueError('Compact snapshot exceeds 5 MB; no import performed.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.', suffix='.pending', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def sync(root=ROOT, client=None):
    with pipeline_lock(root):
        return _sync(root, client)


def _sync(root, client):
    root = Path(root)
    if client is None:
        client = JiraClient(*load_credentials(root))
    prior = read_existing(root)
    raw_issues = fetch_issues(client)
    stamp = now()
    contexts = {key: normalize_issue(issue, fetch_comments(client, key), stamp)
                for key, issue in raw_issues.items()}
    linked_contexts = {}
    inaccessible_links = []
    linked_keys = {link['linkedKey'] for context in contexts.values() for link in context['links']}
    for key in sorted(linked_keys - contexts.keys()):
        try:
            issue = client.get('/rest/api/3/issue/' + urllib.parse.quote(key, safe=''), {'fields': FIELDS})
            linked_contexts[key] = normalize_issue(issue, fetch_comments(client, key), stamp)
        except ValueError as error:
            # Jira can expose a link to an issue the current account cannot read.
            # Expose this source gap to analysis instead of silently assuming its state.
            if 'HTTP 403' in str(error) or 'HTTP 404' in str(error):
                inaccessible_links.append({'key': key, 'reason': 'Jira не надав доступ до повного контексту.'})
            else:
                raise
    all_contexts = {**contexts, **linked_contexts}
    for context in all_contexts.values():
        context['fingerprint'] = fingerprint(context, all_contexts)
    generated = now()
    tasks = [make_task(context, prior.get(key, {})) for key, context in contexts.items()]
    snapshot = {'generatedAt': generated, 'source': 'Jira API — read-only full context sync',
                'jql': JQL, 'complete': True, 'retrievedCount': len(tasks), 'tasks': tasks}
    # Check size before touching either file, preserving the previous complete import on failure.
    if len(json.dumps(snapshot, ensure_ascii=False, indent=2).encode('utf-8')) > SNAPSHOT_LIMIT:
        raise ValueError('Compact snapshot exceeds 5 MB; no import performed.')
    cache = {'generatedAt': generated, 'retrievedAt': stamp, 'jql': JQL, 'complete': True,
             'retrievedCount': len(tasks), 'issues': contexts, 'linkedIssues': linked_contexts,
             'unavailableLinkedIssues': inaccessible_links}
    atomic_json(root / 'data' / 'jira_context.json', cache)
    atomic_json(root / 'inbox' / 'CCON_BA_Snapshot.json', snapshot, SNAPSHOT_LIMIT)
    return {'retrievedCount': len(tasks), 'linkedIssueCount': len(linked_contexts),
            'commentCount': sum(len(issue['comments']) for issue in all_contexts.values()),
            'awaitingAnalysis': sum(task.get('aiStatus') == 'NOT ANALYZED' for task in tasks),
            'generatedAt': generated, 'complete': True}


def main():
    parser = argparse.ArgumentParser(description='Read all in-scope CCON issues and comments; never writes to Jira.')
    parser.add_argument('--root', type=Path, default=ROOT, help='Desk folder for credentials, data and inbox.')
    args = parser.parse_args()
    try:
        result = sync(args.root)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, sqlite3.Error) as error:
        print('Jira sync failed: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
