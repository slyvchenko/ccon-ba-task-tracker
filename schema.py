"""Validation shared by HTTP requests and snapshot/analysis imports."""
import math
from urllib.parse import urlparse
from app_config import SIGNALS

def text_field(value, label, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f'{label} must be text (maximum {maximum:,} characters).')

def validate_draft(draft, label='emailDraft'):
    if not isinstance(draft, dict):
        raise ValueError(label + ' must be an object.')
    for field, maximum in (('to', 2000), ('subject', 2000), ('body', 50000)):
        if field not in draft:
            raise ValueError(label + '.' + field + ' is required.')
        text_field(draft[field], label + '.' + field, maximum)
    if any(char in draft[field] for field in ('to', 'subject') for char in ('\r', '\n')):
        raise ValueError(label + ' recipient and subject must be single-line text.')

def validate_analysis(analysis):
    if not isinstance(analysis, dict):
        raise ValueError('analysis must be an object.')
    if 'signal' in analysis and analysis['signal'] not in SIGNALS:
        raise ValueError('analysis.signal must be READY, WRITE, WAIT, DECIDE, REVIEW or DONE.')
    for field, maximum in (('reasonUk', 20000), ('nextActionUk', 10000),
                           ('waitingOnUk', 2000), ('standardDescription', 30000)):
        if field in analysis:
            text_field(analysis[field], 'analysis.' + field, maximum)
    for field in ('waitingRequired', 'needsEmail'):
        if field in analysis and analysis[field] is not None and not isinstance(analysis[field], bool):
            raise ValueError('analysis.' + field + ' must be true, false or null.')
    if 'stale' in analysis and not isinstance(analysis['stale'], bool):
        raise ValueError('analysis.stale must be true or false.')
    if 'queueScore' in analysis:
        score = analysis['queueScore']
        if isinstance(score, bool) or not isinstance(score, (int, float)) or abs(score) > 1000000 or not math.isfinite(score):
            raise ValueError('analysis.queueScore must be a finite number between -1000000 and 1000000.')
    if 'missingInfo' in analysis:
        missing = analysis['missingInfo']
        if not isinstance(missing, list) or len(missing) > 100:
            raise ValueError('analysis.missingInfo must be an array of at most 100 items.')
        for item in missing:
            text_field(item, 'analysis.missingInfo item', 3000)
    if 'evidence' in analysis:
        evidence = analysis['evidence']
        if not isinstance(evidence, list) or len(evidence) > 100:
            raise ValueError('analysis.evidence must be an array of at most 100 objects.')
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError('analysis.evidence items must be objects.')
            text_field(item.get('text'), 'analysis.evidence.text', 4000)
            text_field(item.get('url'), 'analysis.evidence.url', 2000)
            if item['url'] and urlparse(item['url']).scheme not in ('http', 'https'):
                raise ValueError('analysis.evidence.url must be an HTTP or HTTPS URL.')
    if 'emailDraft' in analysis and analysis['emailDraft'] is not None:
        validate_draft(analysis['emailDraft'], 'analysis.emailDraft')
