"""Validate agent-written analyses against cached Jira context, then import locally."""
import argparse
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
from server import Desk, LIMIT
from pipeline_lock import pipeline_lock, replace_file
from email_rules import normalize_draft
from supplier_logs import verified_method

ROOT=Path(__file__).resolve().parent

def apply(path,root=ROOT):
    with pipeline_lock(root):
        return _apply(path,root)

def _apply(path,root):
    root=Path(root)
    source=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    analyses=source.get('analyses')
    if not isinstance(analyses,dict):
        raise ValueError('Expected analyses object keyed by CCON issue key.')
    context_path=root/'data/jira_context.json'
    target=root/'inbox/CCON_BA_Snapshot.json'
    context_raw=context_path.read_bytes()
    snapshot_raw=target.read_bytes()
    context=json.loads(context_raw.decode('utf-8-sig'))
    if context.get('complete') is not True:
        raise ValueError('Jira context retrieval is incomplete.')
    snapshot=json.loads(snapshot_raw.decode('utf-8-sig'))
    keys={t['key'] for t in snapshot['tasks']}
    if set(context.get('issues',{}))!=keys:
        raise ValueError('Snapshot and Jira context cover different tasks; run Jira sync again.')
    if set(analyses)!=keys:
        raise ValueError(f'Coverage mismatch: {len(keys-analyses.keys())} missing, {len(analyses.keys()-keys)} extra.')
    stamp=datetime.now(timezone.utc).isoformat()
    for task in snapshot['tasks']:
        analysis=analyses[task['key']]
        if not isinstance(analysis,dict):
            raise ValueError('Analysis must be an object for '+task['key'])
        current=context['issues'][task['key']]
        if task.get('contextFingerprint')!=current['fingerprint']:
            raise ValueError('Snapshot and Jira context are from different syncs for '+task['key']+
                             '; run Jira sync again.')
        if analysis.get('contextFingerprint')!=current['fingerprint']:
            raise ValueError('Stale or missing context fingerprint for '+task['key'])
        for field in ('reasonUk','nextActionUk'):
            value=analysis.get(field)
            if not isinstance(value,str) or not value.strip():
                raise ValueError(field+' required for '+task['key'])
            if not any('\u0400'<=char<='\u04ff' for char in value):
                raise ValueError(field+' must be Ukrainian for '+task['key'])
        required={'signal','missingInfo','waitingRequired','waitingOnUk','needsEmail','queueScore','evidence','standardDescription','emailDraft'}
        if not required.issubset(analysis):
            raise ValueError('Incomplete analysis fields for '+task['key'])
        Desk.validate_analysis(analysis)
        analysis['emailDraft']=normalize_draft(task['key'],analysis['emailDraft'],
                                             verified_method(root,task['key'],current['fingerprint']))
        analysis.update(analyzedAt=stamp,stale=False)
        task['analysis']=analysis
        task['contextFingerprint']=current['fingerprint']
    snapshot['generatedAt']=stamp
    desk=Desk(root)
    # Preflight nested types before replacing the import file.
    if hasattr(desk,'validate_analysis'):
        for task in snapshot['tasks']:
            desk.validate_analysis(task['analysis'])
    raw=json.dumps(snapshot,ensure_ascii=False,indent=2)
    if len(raw.encode('utf-8'))>LIMIT:
        raise ValueError('Analyzed snapshot exceeds the import size limit; no files changed.')
    # Also reject edits made by an external program that does not use our lock.
    if context_path.read_bytes()!=context_raw or target.read_bytes()!=snapshot_raw:
        raise ValueError('Jira context or snapshot changed during analysis import; try again with current data.')
    temp=target.with_suffix('.pending')
    temp.write_text(raw,encoding='utf-8')
    replace_file(temp,target)
    result=desk.import_snapshot()
    print(json.dumps({'analyzed':len(keys),'message':result['message']},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('analysis_file',type=Path)
    args=parser.parse_args()
    try:
        apply(args.analysis_file)
    except (ValueError,OSError) as error:
        print('Analysis import failed: '+str(error),file=sys.stderr)
        raise SystemExit(1)
