"""Daily BA delta helpers for the agent-driven analysis run (`/daily-ba`).

Read-only: never writes Jira, never sends e-mail, never changes the snapshot.

    python daily_delta.py list                 # tasks that need (re)analysis today
    python daily_delta.py dump CCON-1 CCON-2   # compact Jira context + previous analysis
    python daily_delta.py errors "PHRASE" ...  # PROD error counts in Elasticsearch (VPN)
    python daily_delta.py check FILE           # quality gate for a partial analyses file

A task needs analysis when it has no analysis, its analysis fingerprint differs
from the current Jira context (content changed), or the stored quality gate is
not STRUCTURALLY_VERIFIED. The agent analyses only these tasks and imports them
with `apply_analysis.py FILE --issues KEY,...`.
"""
import argparse
import json
import sys
from pathlib import Path

from app_config import ROOT
from ba_quality_gate import quality_gate
from review_report import diagnostics

VERIFIED = 'STRUCTURALLY_VERIFIED'


def _load(root):
    root = Path(root)
    snapshot = json.loads((root / 'inbox/CCON_BA_Snapshot.json').read_text(encoding='utf-8-sig'))
    context = json.loads((root / 'data/jira_context.json').read_text(encoding='utf-8-sig'))
    if context.get('complete') is not True:
        raise ValueError('Jira context is incomplete; run jira_sync.py first.')
    return snapshot, context


def worklist(root=ROOT):
    """Tasks needing analysis, highest previous queue score first."""
    snapshot, context = _load(root)
    issues = context['issues']
    rows = []
    for task in snapshot['tasks']:
        key = task['key']
        analysis = task.get('analysis') if isinstance(task.get('analysis'), dict) else {}
        current = issues.get(key, {}).get('fingerprint')
        if not analysis or not analysis.get('signal'):
            reason = 'NEW'
        elif analysis.get('stale') or analysis.get('contextFingerprint') != current:
            reason = 'CHANGED'
        elif (analysis.get('qualityGate') or {}).get('state') != VERIFIED:
            reason = 'QUALITY'
        else:
            continue
        rows.append({'key': key, 'reason': reason, 'summary': task.get('summary', '')[:90],
                     'jiraStatus': task.get('jiraStatus'), 'activeSprint': bool(task.get('activeSprint')),
                     'previousScore': analysis.get('queueScore') or 0})
    order = {'CHANGED': 0, 'NEW': 1, 'QUALITY': 2}
    rows.sort(key=lambda r: (not r['activeSprint'], order[r['reason']], -r['previousScore']))
    return rows


def dump(keys, root=ROOT, comment_limit=2500):
    snapshot, context = _load(root)
    tasks = {task['key']: task for task in snapshot['tasks']}
    issues, linked = context['issues'], context.get('linkedIssues', {})
    out = []
    for key in keys:
        if key not in issues:
            raise ValueError(key + ' is not in the current Jira context.')
        issue, task = issues[key], tasks.get(key, {})
        analysis = task.get('analysis') or {}
        links = [(link.get('type'), link.get('direction'), link['linkedKey'],
                  (issues.get(link['linkedKey']) or linked.get(link['linkedKey']) or {}).get('jiraStatus'))
                 for link in issue.get('links', [])]
        out.append(f"===== {key} | {issue['summary']} | {issue['jiraStatus']} {issue.get('issueType')} "
                   f"{issue.get('priority')} | created {issue.get('createdAt', '')[:10]} | labels {issue.get('labels')} "
                   f"| parent {issue.get('parentKey')} | sprint {task.get('activeSprintNames')}")
        out.append(f"links {links}")
        out.append(f"attachments {[a.get('filename') for a in issue.get('attachments', [])]}")
        out.append('--- DESC')
        out.append(issue.get('description') or '')
        for comment in issue.get('comments', []):
            body = comment.get('body') or comment.get('text') or ''
            author = (comment.get('author') or {}).get('displayName')
            extra = f' …[+{len(body) - comment_limit}]' if len(body) > comment_limit else ''
            out.append(f"--- COMMENT {author} {comment.get('created', '')[:10]}")
            out.append(body[:comment_limit] + extra)
        out.append(f"--- PREVIOUS {analysis.get('signal')} {analysis.get('queueScore')} "
                   f"{(analysis.get('qualityGate') or {}).get('state')}")
        out.append('next: ' + str(analysis.get('nextActionUk') or ''))
        out.append('')
    return '\n'.join(out)


def errors(phrases, root=ROOT, days=90):
    """PROD error counts per phrase (field `error`, domain error). Counts only, no bodies."""
    from es_logs import config, _request
    url, index = config(root)
    result = {}
    for phrase in phrases:
        body = {'size': 1, '_source': ['cconFlowId', '@timestamp'], 'sort': [{'@timestamp': 'desc'}],
                'track_total_hits': True,
                'query': {'bool': {'filter': [{'term': {'domain.keyword': 'error'}},
                                              {'range': {'@timestamp': {'gte': f'now-{days}d'}}},
                                              {'match_phrase': {'error': phrase}}]}},
                'aggs': {'supplier': {'terms': {'field': 'supplier.keyword', 'size': 6}},
                         'method': {'terms': {'field': 'requestorMethodName.keyword', 'size': 6}},
                         'last30': {'filter': {'range': {'@timestamp': {'gte': 'now-30d'}}}},
                         'last7': {'filter': {'range': {'@timestamp': {'gte': 'now-7d'}}}}}}
        data = _request(url, f'/{index}/_search', body)
        aggs, hits = data['aggregations'], data['hits']['hits']
        result[phrase] = {
            f'{days}d': data['hits']['total']['value'], '30d': aggs['last30']['doc_count'],
            '7d': aggs['last7']['doc_count'],
            'suppliers': {b['key']: b['doc_count'] for b in aggs['supplier']['buckets']},
            'methods': {b['key']: b['doc_count'] for b in aggs['method']['buckets']},
            'last': ({'at': hits[0]['_source']['@timestamp'], 'cconFlowId': hits[0]['_source'].get('cconFlowId')}
                     if hits else None)}
    return result


def check(path, root=ROOT):
    """Quality gate + review diagnostics for a partial analyses file, before import."""
    _, context = _load(root)
    issues = context['issues']
    analyses = json.loads(Path(path).read_text(encoding='utf-8-sig'))['analyses']
    rows, ok = [], True
    for key, analysis in analyses.items():
        if key not in issues:
            rows.append({'key': key, 'state': 'UNKNOWN_TASK'}); ok = False; continue
        fresh = analysis.get('contextFingerprint') == issues[key]['fingerprint']
        gate = quality_gate(analysis, issues[key])
        findings = [f['code'] for f in gate['findings']]
        notes = [d['code'] for d in diagnostics(key, analysis)]
        passed = fresh and gate['state'] == VERIFIED and not notes
        ok = ok and passed
        rows.append({'key': key, 'signal': analysis.get('signal'), 'score': analysis.get('queueScore'),
                     'fresh': fresh, 'state': gate['state'], 'findings': findings, 'diagnostics': notes})
    return ok, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    p_dump = sub.add_parser('dump'); p_dump.add_argument('keys', nargs='+')
    p_err = sub.add_parser('errors'); p_err.add_argument('phrases', nargs='+')
    p_err.add_argument('--days', type=int, default=90)
    p_check = sub.add_parser('check'); p_check.add_argument('file', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            print(json.dumps(worklist(args.root), ensure_ascii=False, indent=1))
        elif args.command == 'dump':
            print(dump(args.keys, args.root))
        elif args.command == 'errors':
            print(json.dumps(errors(args.phrases, args.root, args.days), ensure_ascii=False, indent=1))
        else:
            ok, rows = check(args.file, args.root)
            print(json.dumps(rows, ensure_ascii=False, indent=1))
            return 0 if ok else 2
    except (ValueError, OSError, KeyError) as error:
        print('daily_delta failed: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
