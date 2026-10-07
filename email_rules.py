"""User-approved email conventions, applied to generated drafts."""
import re

def normalize_draft(key, draft):
    result = dict(draft)
    body = result.get('body', '').strip()
    if not body:
        return result
    subject = result.get('subject', '').strip()
    formatted = subject.startswith('AER. ')
    subject = re.sub(r'^AER\.\s*', '', subject, flags=re.I)
    subject = re.sub(r'\s*\[\d+\]\s*$', '', subject)
    subject = re.sub(r'^(?:CCON-\d+\s*(?:/\s*)?)+\s*[:—–-]?\s*', '', subject)
    if ':' in subject:
        operation, detail = subject.split(':', 1)
        detail = detail.strip()
        subject = operation.strip() + '. ' + detail[:1].upper() + detail[1:]
    elif not formatted:
        subject = subject[:1].upper() + subject[1:]
    if key == 'CCON-15344':
        subject = re.sub(r'^Verify-fare\.', 'verify-fare.', subject)
    result['subject'] = 'AER. ' + subject + ' [' + key.split('-')[-1] + ']'
    body = re.sub(r'\A(?:Hi|Hello|Dear)\b[^\n]*\n*', '', body, flags=re.I)
    body = re.split(r'\n(?:Best regards|Kind regards|Regards)[,\s]*\n', body, maxsplit=1, flags=re.I)[0]
    body = re.sub(r'We will add the relevant request ID, timestamp and response excerpt from the linked logs before sending\.?', '', body, flags=re.I)
    body = re.sub(r'^\s*Logs (?:are )?attached for your reference\.?\s*$', '', body, flags=re.I | re.M).strip()
    # Preserve the writer's situation-specific thanks; never shorten the analysis.
    closing = 'Thanks in advance for your endless support.'
    lines = body.splitlines()
    if lines and re.match(r'^(?:Thanks\b|Thank you\b|We appreciate\b)', lines[-1], flags=re.I):
        closing = lines.pop().strip()
        body = '\n'.join(lines).strip()
    result['body'] = 'Dear Team,\n\n' + body + '\n\nLogs are attached for your reference.\n' + closing
    return result

