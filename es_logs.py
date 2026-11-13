"""Fetch CCON flow logs straight from Elasticsearch (the store behind Kibana).

Replaces the manual "open CCON admin in the browser and save the ZIP" step:
for every job of the evidence log plan, the flow's documents are read from
filebeat via the Search API and packed into the SAME ZIP layout the CCON
admin download produces (supplier/<Supplier>/<t>-<op>-<Method>-<seq>-request-body.xml,
rest/..., error/...). The existing pipeline (local_downloads.process ->
supplier_logs.ingest) then validates and prepares the supplier-only archive.

Usage:
  python es_logs.py fetch --issue CCON-15562      # one task
  python es_logs.py fetch                         # all tasks of the evidence plan
  python es_logs.py flow <cconFlowId> --out x.zip # raw flow ZIP, no pipeline

Security: only an explicit field whitelist is requested. HTTP headers
(requestHeaders / request_headers / response_headers) carry API keys and
session cookies and are NEVER requested, stored or printed.
Elasticsearch is reachable inside the company network/VPN without login.
"""
import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile, ZIP_DEFLATED

from app_config import ROOT
from storage import read_json

DEFAULT_URL = 'http://192.168.197.246:9200'
DEFAULT_INDEX = 'filebeat_booking_data-*'
UUID = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')
PAGE = 500
MAX_DOCS = 10000
FIELDS = [  # whitelist; headers are deliberately absent
    'time', '@timestamp', 'domain', 'supplier', 'requestorMethodName', 'request_action',
    'request_method', 'request_url', 'response_code', 'response_time',
    'request_body', 'response_body', 'request_body_rest', 'response_body_rest',
    'request_body_json', 'response_body_json',
    'error', 'message', 'warning_code', 'details', 'category', 'line', 'log.offset',
]
META = ('time', 'domain', 'supplier', 'requestorMethodName', 'request_action', 'request_method',
        'request_url', 'response_code', 'response_time', 'error', 'message', 'warning_code',
        'details', 'category', 'line')


def config(root=ROOT):
    data = read_json(Path(root) / 'log_config.json', {})
    url = data.get('elasticsearchUrl') or DEFAULT_URL
    if not re.fullmatch(r'https?://[A-Za-z0-9.\-]+(?::\d+)?', url):
        raise ValueError('Invalid elasticsearchUrl in log_config.json.')
    return url, data.get('elasticsearchIndex') or DEFAULT_INDEX


def _search(url, index, body, timeout=90):
    request = urllib.request.Request(
        f'{url}/{index}/_search', data=json.dumps(body).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise ValueError(f'Elasticsearch HTTP {error.code}: {error.read()[:300].decode("utf-8", "replace")}') from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ValueError(f'Elasticsearch unreachable ({url}); VPN/office network required: {error}') from None


def fetch_flow(flow, root=ROOT):
    """All documents of one cconFlowId, oldest first, whitelisted fields only."""
    if not isinstance(flow, str) or not UUID.fullmatch(flow):
        raise ValueError('Invalid cconFlowId.')
    url, index = config(root)
    body = {'size': PAGE, '_source': {'includes': FIELDS},
            'query': {'bool': {'filter': [{'term': {'cconFlowId.keyword': flow}}]}},
            'sort': [{'time': 'asc'}, {'log.offset': 'asc'}], 'track_total_hits': True}
    docs = []
    while True:
        result = _search(url, index, body)
        hits = result.get('hits', {}).get('hits', [])
        docs.extend(hit['_source'] for hit in hits)
        if len(hits) < PAGE or len(docs) >= MAX_DOCS:
            return docs[:MAX_DOCS]
        body['search_after'] = hits[-1]['sort']


def _micro(value):
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return str(int(moment.timestamp() * 1_000_000))
    except ValueError:
        return '0'


def _slug(value, pattern=r'[^A-Za-z0-9\-]+'):
    return re.sub(pattern, '-', str(value or '')).strip('-')[:60]


SECRET_XML = re.compile(
    r'(<(?:[\w.\-]+:)?(?:Password|Nonce|BinarySecurityToken|ClientSecret|ApiKey|AccessToken)\b[^>]*>)(.*?)(</)', re.S | re.I)
SECRET_JSON = re.compile(
    r'("(?:password|passwd|pwd|apikey|api_key|x-api-key|token|access_token|refresh_token|secret|client_secret|authorization)"\s*:\s*)"(?:[^"\\]|\\.)*"', re.I)
SECRET_ATTR = re.compile(r'((?:password|apikey|token|secret)\s*=\s*)("[^"]*"|\'[^\']*\')', re.I)


def redact(text):
    """Mask credentials inside bodies before anything is written to disk."""
    text = SECRET_XML.sub(lambda m: m.group(1) + '***' + m.group(3), text)
    text = SECRET_JSON.sub(lambda m: m.group(1) + '"***"', text)
    return SECRET_ATTR.sub(lambda m: m.group(1) + '"***"', text)


def _text(value):
    if value in (None, ''):
        return ''
    return redact(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))


def build_zip(docs):
    """Pack documents in the CCON admin 'logs-download' layout."""
    buffer = io.BytesIO()
    counts = {}
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for seq, doc in enumerate(docs):
            domain = _slug(doc.get('domain') or 'other', r'[^A-Za-z0-9_\-]+') or 'other'
            stamp, op = _micro(doc.get('time') or doc.get('@timestamp')), _slug(doc.get('requestorMethodName')) or 'flow'
            meta = {k: doc[k] for k in META if k in doc}
            if isinstance(meta.get('request_url'), str):  # never keep query strings
                parts = urlsplit(meta['request_url'])
                meta['request_url'] = (f'{parts.scheme}://{parts.netloc}' if parts.netloc else '') + parts.path
            if domain == 'supplier':
                folder = 'supplier/' + (_slug(doc.get('supplier'), r'[^A-Za-z0-9_]+') or 'Unknown')
                method = _slug(doc.get('request_action'), r'[^A-Za-z0-9_]+')
                rq, rs = _text(doc.get('request_body')), _text(doc.get('response_body'))
                if method and re.match(r'[A-Za-z]', method) and (rq or rs):
                    if rq:
                        archive.writestr(f'{folder}/{stamp}-{op}-{method}-{seq}-request-body.xml', rq)
                    if rs:
                        archive.writestr(f'{folder}/{stamp}-{op}-{method}-{seq}-response-body.xml', rs)
                archive.writestr(f'{folder}/{stamp}-{op}-rq-rs-{seq}.txt', _text(meta))
            elif domain == 'rest':
                rq = _text(doc.get('request_body_json') or doc.get('request_body_rest'))
                rs = _text(doc.get('response_body_json') or doc.get('response_body_rest'))
                if rq:
                    archive.writestr(f'rest/{stamp}-{op}-request-body-{seq}.json', rq)
                if rs:
                    archive.writestr(f'rest/{stamp}-{op}-response-body-{seq}.json', rs)
                archive.writestr(f'rest/{stamp}-{op}-rq-rs-{seq}.txt', _text(meta))
            else:
                archive.writestr(f'{domain}/{stamp}-{op}-{seq}.txt', _text(meta))
            counts[domain] = counts.get(domain, 0) + 1
    return buffer.getvalue(), counts


def save_flow_zip(flow, target, root=ROOT):
    docs = fetch_flow(flow, root)
    if not docs:
        return {'flowId': flow, 'documents': 0, 'saved': False}
    data, counts = build_zip(docs)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.part')
    temp.write_bytes(data)
    temp.replace(target)
    return {'flowId': flow, 'documents': len(docs), 'domains': counts, 'bytes': len(data), 'saved': True}


def fetch_for_plan(root=ROOT, issue=None):
    """Prepare the evidence plan, fill each job's ZIP from Elasticsearch, then process."""
    from local_downloads import prepare, process
    handoff = prepare(root, issue)
    fetched = []
    for job in handoff['jobs']:
        if job.get('cached'):
            fetched.append({'issueKey': job['issueKey'], 'flowId': job['flowId'], 'cached': True})
            continue
        try:
            row = save_flow_zip(job['flowId'], job['saveAs'], root)
        except ValueError as error:
            row = {'flowId': job['flowId'], 'saved': False, 'error': str(error)}
        fetched.append({'issueKey': job['issueKey'], **row})
    return {'fetched': fetched, 'skipped': handoff.get('skipped', []), 'processed': process(root, issue)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='action', required=True)
    one = sub.add_parser('fetch')
    one.add_argument('--issue')
    raw = sub.add_parser('flow')
    raw.add_argument('flow')
    raw.add_argument('--out', required=True)
    args = parser.parse_args()
    result = fetch_for_plan(ROOT, args.issue) if args.action == 'fetch' else save_flow_zip(args.flow, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
