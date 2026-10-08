"""Plan authenticated CCON downloads and prepare immutable supplier XML bundles.

The daily agent opens downloadUrl in its authenticated CCON browser session.
No browser cookies, passwords, or session tokens are copied into this script.
"""
import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

from pipeline_lock import pipeline_lock, replace_file

ROOT = Path(__file__).resolve().parent
CCON_DOWNLOAD = 'https://cconnector.aerticket-it.de/admin/logs-download/'
MAX_ZIP = 100 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
VERSION = 2
XML_NAME = re.compile(r'\d+-(?P<operation>.+)-(?P<method>[A-Za-z][A-Za-z0-9_]*)-(?P<seq>\d+)-(?P<kind>request-body|response-body)\.xml', re.I)
SUPPLIERS = [
    (r'^Airtuerk\b', 'Airtuerk', ['Airtuerk']),
    (r'^(?:AF\s*/\s*KL|AFKL)\b', 'AirFranceKLM', ['AirFranceKLM', 'AFKL']),
    (r'^SQ213\b', 'SQ213', ['SQ213']),
    (r'^(?:FinnAir|Finnair|AY)\b', 'FinnAir', ['FinnAir', 'Finnair']),
    (r'^TAP\b', 'TAP', ['TAP']),
    (r'^FlyDubai\b', 'FlyDubai', ['FlyDubai']),
]


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    replace_file(temp, path)


def logs_root(root):
    config = read_json(Path(root) / 'log_config.json', {})
    configured = config.get('logsDir')
    return Path(configured).resolve() if isinstance(configured, str) and configured else (Path(root) / 'logs').resolve()


def inside(parent, relative):
    path = (parent / relative).resolve()
    if not path.is_relative_to(parent.resolve()):
        raise ValueError('Invalid stored log path.')
    return path


def validate_identity(key, flow):
    if not re.fullmatch(r'CCON-\d+', key) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', flow):
        raise ValueError('Invalid task key or cconFlowId.')


def download_url(flow):
    validate_identity('CCON-1', flow)
    return CCON_DOWNLOAD + '?' + urlencode({'cconFlowId': flow, 'pnrCode': ''})


def links_in(value):
    if isinstance(value, dict):
        attrs = value.get('attrs') or {}
        for field in ('href', 'url'):
            if isinstance(attrs.get(field), str):
                yield attrs[field]
        for child in value.values():
            yield from links_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from links_in(child)
    elif isinstance(value, str):
        yield from re.findall(r'https?://[^\s<>"\]]+', value)


def flow_references(issue):
    """Only UUIDs in Kibana cconFlowId filters, including wrapped Safe Links."""
    found = {}
    for original in links_in({'description': issue.get('descriptionAdf', issue.get('description')),
                              'comments': issue.get('comments', [])}):
        url = original
        for _ in range(3):
            try:
                parsed = urlparse(url)
            except ValueError:
                break
            if (parsed.hostname or '').endswith('.safelinks.protection.outlook.com'):
                nested = parse_qs(parsed.query).get('url', [])
                if nested:
                    url = nested[0]
                    continue
            break
        try:
            parsed = urlparse(url)
            allowed = parsed.hostname == '192.168.197.246' and parsed.port == 5601 and parsed.path == '/app/kibana'
        except ValueError:
            continue
        if not allowed:
            continue
        decoded = unquote(parsed.fragment)
        if not re.search(r'key:\s*\'?cconFlowId\'?', decoded):
            continue
        # Limit matching to the named filter so unrelated UUIDs are never used.
        for block in re.findall(r'key:\s*\'?cconFlowId\'?.*?(?=\),query:|$)', decoded):
            for flow in re.findall(r"(?:query|value):\s*'?([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", block, re.I):
                found.setdefault(flow.lower(), url)
    return [{'flowId': flow, 'sourceUrl': url} for flow, url in found.items()]


def supplier_hint(summary):
    for pattern, name, aliases in SUPPLIERS:
        if re.search(pattern, summary, re.I):
            return {'name': name, 'aliases': aliases}
    return None


def make_plan(root=ROOT, analysis_file=None, issue_key=None):
    from server import Desk
    root = Path(root)
    with pipeline_lock(root):
        context = read_json(root / 'data/jira_context.json', {})
        if context.get('complete') is not True:
            raise ValueError('A complete Jira sync is required before planning logs.')
        proposed = read_json(analysis_file, {}).get('analyses', {}) if analysis_file else None
        view = Desk(root).view()
        directory = logs_root(root)
        index = read_json(directory / 'index.json', {})
        jobs, skipped = [], []
        for task in view['tasks']:
            key = task['key']
            if issue_key and key != issue_key:
                continue
            analysis = proposed.get(key, {}) if proposed is not None else task.get('analysis', {})
            if not task.get('active') or task.get('manualStatus', 'AUTO') != 'AUTO' or analysis.get('signal') != 'WRITE' or analysis.get('needsEmail') is not True:
                continue
            issue = context.get('issues', {}).get(key, {})
            fingerprint = issue.get('fingerprint')
            if not fingerprint or analysis.get('contextFingerprint') != fingerprint or analysis.get('stale'):
                skipped.append({'key': key, 'reason': 'stale_analysis'})
                continue
            supplier = supplier_hint(task['summary'])
            references = flow_references(issue)
            if not supplier or not references:
                skipped.append({'key': key, 'reason': 'supplier_unknown' if not supplier else 'no_flow_id'})
                continue
            for reference in references:
                flow = reference['flowId']
                entry = index.get(key + '/' + flow, {})
                cached = False
                if (entry.get('version') == VERSION and entry.get('contextFingerprint') == fingerprint
                        and entry.get('checkedAt', '')[:10] == now()[:10]):
                    try:
                        archive = inside(directory, entry['archiveRelativePath'])
                        cached = archive.is_file() and digest(archive.read_bytes()) == entry['archiveSha256']
                    except (KeyError, OSError, ValueError):
                        pass
                jobs.append({'key': key, **reference, 'downloadUrl': download_url(flow),
                             'summary': task['summary'], 'supplier': supplier,
                             'contextFingerprint': fingerprint, 'cached': cached,
                             'archiveRelativePath': entry.get('archiveRelativePath') if cached else None})
        plan = {'generatedAt': now(), 'logsDirectory': str(directory), 'jobs': jobs, 'skipped': skipped}
        write_json(root / 'data/log_plan.json', plan)
        return plan


def local_tag(element):
    return element.tag.rsplit('}', 1)[-1].lower()


def response_errors(data):
    if b'<!DOCTYPE' in data.upper():
        return [], 'XML contains a DTD; error extraction needs review.'
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return [], 'Response XML could not be parsed; original bytes preserved.'
    errors = []
    for element in root.iter():
        if local_tag(element) not in ('providererror', 'error', 'applicationerror', 'fault'):
            continue
        values = {local_tag(child): ' '.join(' '.join(child.itertext()).split()) for child in element.iter()}
        code = element.attrib.get('Code', element.attrib.get('code', '')) or next((values[k] for k in ('code', 'errorcode', 'faultcode') if values.get(k)), '')
        text = ' '.join(' '.join(element.itertext()).split())[:5000]
        if text or code:
            record = {'code': code[:500], 'text': text}
            if record not in errors:
                errors.append(record)
    return errors[:100], None


def inspect_bundle(raw, aliases, summary):
    if len(raw) > MAX_ZIP:
        raise ValueError('Archive exceeds 100 MB.')
    groups, warnings = defaultdict(dict), []
    try:
        with ZipFile(io.BytesIO(raw)) as source:
            members = source.infolist()
            if len(members) > 10000 or sum(i.file_size for i in members) > MAX_EXPANDED:
                raise ValueError('Archive expanded size exceeds the limit.')
            paths = [(item, PurePosixPath(item.filename.replace('\\', '/'))) for item in members if not item.is_dir()]
            if any(path.is_absolute() or '..' in path.parts or ':' in str(path) for _, path in paths):
                raise ValueError('Unsafe path in ZIP.')
            suppliers = {path.parts[1] for _, path in paths if len(path.parts) > 2 and path.parts[0] == 'supplier'}
            matches = [name for name in suppliers if name.casefold() in {alias.casefold() for alias in aliases}]
            if len(matches) != 1:
                raise ValueError('Expected supplier folder is missing or ambiguous.')
            supplier = matches[0]
            for item, path in paths:
                if path.parts[:2] != ('supplier', supplier) or path.suffix.lower() != '.xml':
                    continue
                match = XML_NAME.fullmatch(path.name)
                if not match:
                    raise ValueError('Unrecognized supplier XML filename: ' + path.name)
                seq = int(match['seq'])
                kind = 'RQ' if match['kind'].lower() == 'request-body' else 'RS'
                if kind in groups[seq] or (groups[seq] and next(iter(groups[seq].values()))['method'] != match['method']):
                    raise ValueError('Ambiguous supplier exchange sequence: ' + str(seq))
                if item.file_size > 32 * 1024 * 1024:
                    raise ValueError('Supplier XML exceeds 32 MB.')
                data = source.read(item)
                errors, warning = response_errors(data) if kind == 'RS' else ([], None)
                if warning:
                    warnings.append({'seq': seq, 'message': warning})
                groups[seq][kind] = {**match.groupdict(), 'data': data, 'source': item.filename, 'errors': errors}
    except (BadZipFile, RuntimeError, NotImplementedError):
        raise ValueError('Download is not a supported, unencrypted ZIP archive.') from None
    if not groups:
        raise ValueError('Supplier has no request/response XML.')
    errors, files = [], []
    methods = set()
    for number, (seq, pair) in enumerate(sorted(groups.items()), 1):
        if set(pair) != {'RQ', 'RS'}:
            warnings.append({'seq': seq, 'message': 'Request or response is missing.'})
        for kind in ('RQ', 'RS'):
            if kind not in pair:
                continue
            item = pair[kind]
            methods.add(item['method'])
            files.append({**item, 'seq': seq, 'kind': kind, 'output': f'{number:02d}-{item["method"]}{kind}.xml'})
            errors.extend({'seq': seq, 'method': item['method'], 'operation': item['operation'], **error} for error in item['errors'])
    target_codes = set(re.findall(r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b', summary))
    matched = [error for error in errors if any(code in error['text'] or code == error['code'] for code in target_codes)]
    operations = summary.split('.')
    operation = operations[1].strip().casefold() if len(operations) > 1 else ''
    candidates = {error['method'] for error in matched}
    if not target_codes:
        candidates = {error['method'] for error in errors if error['operation'].casefold() == operation}
        if not candidates:
            candidates = {item['method'] for item in files if item['operation'].casefold() == operation}
        if not candidates and len(methods) == 1:
            candidates = methods
    preferred = next(iter(candidates)) if len(candidates) == 1 else None
    if not preferred:
        warnings.append({'message': 'Failing supplier method is ambiguous or the task error was not found; review before drafting.'})
    return {'supplier': supplier, 'files': files, 'methods': sorted(methods),
            'preferredMethod': preferred, 'errors': errors, 'matchedErrors': matched, 'warnings': warnings,
            'exchangeCount': len(groups)}


def label(value, fallback, maximum=32):
    result = re.sub(r'[^A-Za-z0-9_]+', '-', value).strip('-')[:maximum]
    return result or fallback


def ingest(root, key, flow, source_path):
    root = Path(root).resolve()
    validate_identity(key, flow)
    with pipeline_lock(root):
        plan = read_json(root / 'data/log_plan.json', {})
        job = next((job for job in plan.get('jobs', []) if job['key'] == key and job['flowId'] == flow), None)
        if not job:
            raise ValueError('Run plan first; this task and flow are not in the log plan.')
        context = read_json(root / 'data/jira_context.json', {})
        if context.get('issues', {}).get(key, {}).get('fingerprint') != job['contextFingerprint']:
            raise ValueError('Jira context changed; regenerate the log plan.')
        from server import Desk
        task = next((task for task in Desk(root).view()['tasks'] if task['key'] == key), None)
        if not task or not task['active'] or task['manualStatus'] != 'AUTO':
            raise ValueError('Task is no longer eligible for automatic log preparation.')
        source_path = Path(source_path)
        if source_path.stat().st_size > MAX_ZIP:
            raise ValueError('Archive exceeds 100 MB.')
        raw = source_path.read_bytes()
        source_hash = digest(raw)
        bundle = inspect_bundle(raw, job['supplier']['aliases'], job['summary'])
        content_hash = digest(json.dumps([{'source': item['source'], 'output': item['output'], 'sha256': digest(item['data'])}
                                          for item in bundle['files']], sort_keys=True).encode())
        error_label = next((code for code in re.findall(r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b', job['summary'])
                            if any(code in error['text'] or code == error['code'] for error in bundle['matchedErrors'])), 'Logs')
        name = '-'.join([label(bundle['supplier'], 'Supplier', 20), label(bundle['preferredMethod'] or '', 'MultipleMethods'),
                         label(error_label.removeprefix('TOURCONEX_'), 'Logs', 24), key])
        directory = logs_root(root)
        parent = directory / key / flow
        parent.mkdir(parents=True, exist_ok=True)
        selector = digest(json.dumps({'version': VERSION, 'summary': job['summary'], 'supplier': job['supplier']}, sort_keys=True).encode())[:8]
        version_dir = parent / (content_hash[:12] + '-' + selector)
        if version_dir.exists():
            # Validate a previous result before reusing it; never overwrite files.
            facts = read_json(version_dir / 'facts.json', {})
            archive = version_dir / facts.get('archiveName', 'missing.zip')
            if (facts.get('version') != VERSION or facts.get('contentSha256') != content_hash
                    or not archive.is_file() or digest(archive.read_bytes()) != facts.get('archiveSha256')
                    or digest((version_dir / 'original.zip').read_bytes()) != facts.get('sourceSha256')):
                raise ValueError('Existing log result is damaged; preserve it for review.')
        else:
            # Inherit the workspace ACL on Windows, as the rest of the desk does.
            stage = parent / ('.prepare-' + uuid.uuid4().hex[:8])
            stage.mkdir()
            try:
                (stage / 'original.zip').write_bytes(raw)
                folder = stage / name
                folder.mkdir()
                archive = stage / (name + '.zip')
                mapping = []
                with ZipFile(archive, 'x', ZIP_DEFLATED) as output:
                    for item in bundle['files']:
                        (folder / item['output']).write_bytes(item['data'])
                        output.writestr(name + '/' + item['output'], item['data'])
                        mapping.append({'seq': item['seq'], 'kind': item['kind'], 'method': item['method'],
                                        'source': item['source'], 'output': item['output'], 'sha256': digest(item['data'])})
                with ZipFile(archive) as output:
                    if output.testzip() is not None or any(digest(output.read(name + '/' + item['output'])) != item['sha256'] for item in mapping):
                        raise ValueError('Output verification failed.')
                facts = {'version': VERSION, 'key': key, 'flowId': flow, 'createdAt': now(), 'sourceSha256': source_hash, 'contentSha256': content_hash,
                         'supplier': bundle['supplier'], 'supplierMethods': bundle['methods'], 'preferredMethod': bundle['preferredMethod'],
                         'fileCount': len(mapping), 'exchangeCount': bundle['exchangeCount'], 'errors': bundle['errors'],
                         'matchedErrors': bundle['matchedErrors'], 'warnings': bundle['warnings'], 'mapping': mapping,
                         'archiveName': archive.name, 'archiveSha256': digest(archive.read_bytes())}
                write_json(stage / 'facts.json', facts)
                stage.rename(version_dir)
            finally:
                if stage.exists():
                    # Only remove this invocation's verified temporary directory.
                    if stage.parent.resolve() == parent.resolve() and stage.name.startswith('.prepare-'):
                        shutil.rmtree(stage)
        archive = version_dir / facts['archiveName']
        entry = {field: facts[field] for field in ('version', 'key', 'flowId', 'sourceSha256', 'archiveSha256', 'fileCount', 'exchangeCount', 'supplier', 'preferredMethod', 'warnings')}
        entry.update(checkedAt=now(), downloadSha256=source_hash, contextFingerprint=job['contextFingerprint'],
                     archiveRelativePath=archive.relative_to(directory).as_posix(), factsRelativePath=(version_dir / 'facts.json').relative_to(directory).as_posix())
        index = read_json(directory / 'index.json', {})
        index[key + '/' + flow] = entry
        write_json(directory / 'index.json', index)
        return entry


def verified_method(root, key, fingerprint):
    """Use only unambiguous method evidence from the complete current log plan."""
    try:
        return _verified_method(root, key, fingerprint)
    except (ValueError, OSError, KeyError, TypeError):
        # A failed optional log stage must not prevent other Jira analyses.
        return None


def _verified_method(root, key, fingerprint):
    root = Path(root)
    plan = read_json(root / 'data/log_plan.json', {})
    jobs = [job for job in plan.get('jobs', []) if job['key'] == key and job['contextFingerprint'] == fingerprint]
    if not jobs:
        return None
    directory = logs_root(root)
    index = read_json(directory / 'index.json', {})
    methods = set()
    for job in jobs:
        entry = index.get(key + '/' + job['flowId'], {})
        method = entry.get('preferredMethod')
        if entry.get('contextFingerprint') != fingerprint or not method or entry.get('warnings'):
            return None
        try:
            archive = inside(directory, entry['archiveRelativePath'])
            if digest(archive.read_bytes()) != entry['archiveSha256']:
                return None
        except (KeyError, ValueError, OSError):
            return None
        methods.add(method)
    return next(iter(methods)) if len(methods) == 1 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan')
    plan.add_argument('--analysis-file', type=Path)
    plan.add_argument('--issue')
    process = commands.add_parser('ingest')
    process.add_argument('--issue', required=True)
    process.add_argument('--flow-id', required=True)
    process.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = make_plan(args.root, args.analysis_file, args.issue) if args.command == 'plan' else ingest(args.root, args.issue, args.flow_id, args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, BadZipFile) as error:
        print('Log preparation failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
