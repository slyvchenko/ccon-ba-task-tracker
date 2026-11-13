"""Builder for agent-written BA analyses (used by the `/daily-ba` command).

`build()` turns compact tuples into the full analysis object expected by
apply_analysis.py and refuses any source excerpt that is not verbatim in the
issue's own summary, description or comments (the quality gate requires this).

    from analysis_kit import Kit
    kit = Kit()                       # reads data/jira_context.json under ROOT
    analyses = {'CCON-1': kit.build('CCON-1', signal='DECIDE', ...)}
    kit.write(analyses, 'data/partial_analysis_2026-11-14.json')

Conventions enforced by the quality gate (see BA_ANALYSIS_RULES.md):
- facts/rules: (text, excerpt) / (id, whenUk, thenUk, excerpt|None); None = OPEN rule.
- every CONFIRMED rule needs POSITIVE and NEGATIVE QA; add EDGE when whenUk
  contains "і", "або", AND or OR.
- QA lines in the Jira description start with "- Check".
- WRITE requires needs_email=True; WAIT requires waiting=True with a source.
"""
import json
from pathlib import Path

from app_config import ROOT

JIRA = 'https://aerticket.atlassian.net/browse/'
KIBANA = 'http://192.168.197.246:5601/app/kibana#/discover?_a=(query:(language:kuery,query:%27cconFlowId:%22{}%22%27))'


def kibana(flow):
    return KIBANA.format(flow)


class Kit:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.context = json.loads((self.root / 'data/jira_context.json').read_text(encoding='utf-8-sig'))
        self.issues = self.context['issues']

    def corpus(self, key):
        issue = self.issues[key]
        comments = '\n'.join((c.get('body') or c.get('text') or '') for c in issue.get('comments', []))
        return (issue.get('summary') or '') + '\n' + (issue.get('description') or '') + '\n' + comments

    def excerpt(self, key, text):
        if text not in self.corpus(key):
            raise ValueError(f'{key}: excerpt is not verbatim in the issue (check \\xa0 and curly quotes): {text[:80]}')
        return text

    def build(self, key, *, signal, factors, reason, next_, missing, evidence, title, desc, email,
              audience, email_lim, overview, current, target, impact, scope, audit, facts, timeline,
              rules, qa, risks, unknowns, readiness='NEEDS_CONFIRMATION', readiness_reason,
              needs_email=False, waiting=False, waiting_on='Не визначено'):
        if signal == 'WRITE' and not needs_email:
            raise ValueError(f'{key}: WRITE requires needs_email=True.')
        if signal == 'WAIT' and not waiting:
            raise ValueError(f'{key}: WAIT requires waiting=True.')
        url = JIRA + key
        ex = lambda text: self.excerpt(key, text)  # noqa: E731
        return {
            'contextFingerprint': self.issues[key]['fingerprint'],
            'descriptionContextAt': self.issues[key].get('retrievedAt') or self.context.get('retrievedAt'),
            'signal': signal, 'reasonUk': reason, 'nextActionUk': next_, 'missingInfo': missing,
            'waitingRequired': waiting, 'waitingOnUk': waiting_on, 'needsEmail': needs_email,
            'priorityFactors': factors, 'queueScore': sum(factors.values()),
            'evidence': [{'text': t, 'url': url if u is None else u} for t, u in evidence],
            'descriptionTitle': title, 'descriptionState': 'DRAFT', 'standardDescription': desc,
            'emailDraft': email, 'emailDraftAudience': audience, 'emailDraftLimitationsUk': email_lim,
            'preparation': {'status': 'READY' if readiness == 'READY_FOR_REVIEW' else 'NEEDS_INFO',
                            'reasonUk': readiness_reason},
            'briefing': {
                'overviewUk': overview, 'currentUk': current, 'targetUk': target,
                'businessImpactUk': impact, 'technicalScopeUk': scope,
                'sourceAudit': [{'descriptionUk': d, 'status': st, 'sourceUrl': url if u is None else u}
                                for d, st, u in audit],
                'confirmedFacts': [{'textUk': t, 'sourceUrl': url, 'sourceExcerpt': ex(e)} for t, e in facts],
                'timeline': [{'date': d, 'eventUk': e, 'status': 'CONFIRMED', 'sourceUrl': url} for d, e in timeline],
                'rules': [dict({'id': rid, 'whenUk': w, 'thenUk': t,
                                'certainty': 'CONFIRMED' if e else 'OPEN', 'sourceUrl': url},
                               **({'sourceExcerpt': ex(e)} if e else {})) for rid, w, t, e in rules],
                'verification': [{'kind': kd, 'scenarioUk': s, 'expectedUk': x, 'ruleIds': ids, 'sourceUrl': url}
                                 for kd, s, x, ids in qa],
                'risksUk': risks, 'unknownsUk': unknowns, 'readiness': readiness,
                'readinessReasonUk': readiness_reason,
            },
        }

    @staticmethod
    def write(analyses, path):
        Path(path).write_text(json.dumps({'analyses': analyses}, ensure_ascii=False, indent=2), encoding='utf-8')
        return Path(path)
