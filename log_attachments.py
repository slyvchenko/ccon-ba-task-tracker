"""Task-scoped access to the supplier ZIPs prepared by the daily pipeline."""
import os
import re
from pathlib import Path
from urllib.parse import quote

from supplier_logs import digest, flow_references, inside, logs_root, read_json, supplier_hint, validate_identity


def validate_key(key):
    if not isinstance(key, str) or not re.fullmatch(r'CCON-\d+', key):
        raise ValueError('Некоректний номер задачі.')


def archive_path(directory, key, flow, entry):
    validate_identity(key, flow)
    if entry.get('key') != key or entry.get('flowId') != flow:
        raise ValueError('Архів не відповідає задачі.')
    parent = inside(directory, key + '/' + flow)
    path = inside(directory, entry['archiveRelativePath'])
    if not path.is_relative_to(parent) or not path.name.endswith('-' + key + '.zip') or not path.is_file():
        raise ValueError('Архів не знайдено в папці задачі.')
    return path


def log_catalog(desk, key=None):
    if key is not None:
        validate_key(key)
    tasks = {task['key']: task for task in desk.view()['tasks']}
    if key is not None and key not in tasks:
        raise ValueError('Задачу не знайдено.')
    directory = logs_root(desk.root)
    context = read_json(Path(desk.root) / 'data/jira_context.json', {})
    index = read_json(directory / 'index.json', {})
    if not isinstance(index, dict) or not isinstance(context, dict):
        raise ValueError('Не вдалося прочитати індекс логів або контекст Jira.')
    result = {task_key: {'key': task_key, 'items': [], 'folder': str(directory / task_key),
                         'folderAvailable': inside(directory, task_key).is_dir()}
              for task_key in ([key] if key else tasks)}
    for identity, entry in index.items():
        if not isinstance(identity, str) or not isinstance(entry, dict):
            continue
        task_key, separator, flow = identity.partition('/')
        if not separator or task_key not in result:
            continue
        try:
            path = archive_path(directory, task_key, flow, entry)
        except (ValueError, OSError, KeyError, TypeError):
            continue
        fingerprint = context.get('issues', {}).get(task_key, {}).get('fingerprint')
        result[task_key]['items'].append({
            'flowId': flow, 'filename': path.name, 'sizeBytes': path.stat().st_size,
            'method': entry.get('preferredMethod'), 'supplier': entry.get('supplier'),
            'fileCount': entry.get('fileCount'), 'checkedAt': entry.get('checkedAt'),
            'needsReview': bool(entry.get('warnings')),
            'stale': not fingerprint or entry.get('contextFingerprint') != fingerprint,
            'downloadUrl': '/api/logs/' + quote(task_key) + '/' + quote(flow) + '/download',
        })
    for item in result.values():
        item['items'].sort(key=lambda attachment: (attachment['checkedAt'] or '', attachment['flowId']), reverse=True)
        issue = context.get('issues', {}).get(item['key'], {})
        expected = {reference['flowId'] for reference in flow_references(issue)}
        prepared = {attachment['flowId'] for attachment in item['items'] if not attachment['stale']}
        item['pendingCount'] = len(expected - prepared)
        item['emptyMessage'] = ('Контекст Jira ще не завантажено.' if not issue else
                                'У Jira не знайдено cconFlowId для завантаження логів.' if not expected else
                                'Потрібно уточнити постачальника для обробки логів.' if not supplier_hint(tasks[item['key']]['summary']) else
                                'Логи ще не підготовлені. Після щоденної обробки архіви цієї задачі з’являться тут.')
    return result[key] if key else result


def download_archive(desk, key, flow):
    validate_identity(key, flow)
    if not any(task['key'] == key for task in desk.view()['tasks']):
        raise ValueError('Задачу не знайдено.')
    directory = logs_root(desk.root)
    index = read_json(directory / 'index.json', {})
    if not isinstance(index, dict):
        raise ValueError('Не вдалося прочитати індекс логів.')
    entry = index.get(key + '/' + flow, {})
    if not isinstance(entry, dict):
        raise ValueError('Некоректний запис архіву.')
    path = archive_path(directory, key, flow, entry)
    content = path.read_bytes()
    if digest(content) != entry.get('archiveSha256'):
        raise ValueError('Архів змінено або пошкоджено. Потрібна повторна підготовка логів.')
    return path.name, content


def open_task_folder(desk, key, opener=None):
    validate_key(key)
    if not any(task['key'] == key for task in desk.view()['tasks']):
        raise ValueError('Задачу не знайдено.')
    path = inside(logs_root(desk.root), key)
    if not path.is_dir():
        raise ValueError('Папка з’явиться після підготовки логів.')
    if opener is None:
        if not hasattr(os, 'startfile'):
            raise ValueError('Відкриття папки доступне на Windows.')
        opener = os.startfile
    opener(str(path))
    return {'message': 'Папку логів відкрито.'}
