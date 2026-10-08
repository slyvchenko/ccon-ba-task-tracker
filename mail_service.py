"""Validated Windows mailto handoff; does not send email."""
import os
import re
from email.utils import getaddresses
from urllib.parse import quote, urlencode
from schema import validate_draft

def open_email_batch(items, opener=None):
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ValueError('Оберіть від 1 до 100 чернеток.')
    urls, keys = [], set()
    for item in items:
        if not isinstance(item, dict) or not re.fullmatch(r'CCON-\d+', str(item.get('key', ''))):
            raise ValueError('Некоректний номер задачі.')
        key = item['key']
        if key in keys:
            raise ValueError('Задача повторюється у списку.')
        keys.add(key)
        draft = item.get('draft')
        validate_draft(draft)
        addresses = [address for _, address in getaddresses([draft['to']])]
        if not addresses or any(not re.fullmatch(r'[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+', address) for address in addresses):
            raise ValueError(key + ': перевірте адресатів.')
        if not draft['subject'].strip() or not draft['body'].strip():
            raise ValueError(key + ': потрібні тема й текст листа.')
        url = 'mailto:' + quote(','.join(addresses), safe='@,') + '?' + urlencode(
            {'subject': draft['subject'], 'body': draft['body']}, quote_via=quote)
        urls.append((key, url))
    if opener is None:
        if not hasattr(os, 'startfile'):
            raise ValueError('Відкриття пошти доступне на Windows.')
        opener = os.startfile
    opened, failed = [], []
    for key, url in urls:
        try:
            opener(url)
            opened.append(key)
        except OSError:
            failed.append(key)
    return {'opened': opened, 'failed': failed}
