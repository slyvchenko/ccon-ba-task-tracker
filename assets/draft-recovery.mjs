// Browser-only crash recovery with one durable localStorage record PER TAB.
// No cross-tab last-writer-wins and no silent deletion of private drafts.
// The backend's manualRevision CAS remains the final write protection.
export const LEGACY_DRAFT_KEY = 'ccon-ba-desk.unsaved-forms.v2';
export function nextRecoverySource(others,previousId=null) {
  if (!Array.isArray(others) || !others.length) return null;
  const index=others.findIndex(source=>source.id===previousId);
  return others[(index+1)%others.length];
}

export const TAB_ID_KEY = 'ccon-ba-desk.recovery-tab.v3';
export const RECORD_PREFIX = 'ccon-ba-desk.unsaved-tab.v3.';
export const RETENTION_DAYS = 30;

// Reading window.localStorage/sessionStorage can itself throw SecurityError,
// before any .getItem() guard in createDraftRecoveryStore can run.
export function safeBrowserStorage(readStorage) {
  try { return readStorage(); }
  catch {
    const denied=()=>{throw Error('Browser storage denied');};
    return {getItem:denied,setItem:denied,removeItem:denied,
      key:denied,get length(){return 0;}};
  }
}
const ISSUE = /^CCON-\d+$/;
const TAB = /^[a-f0-9-]{20,64}$/;
const VALID_STATUS = new Set(['AUTO','IN PROGRESS','WAITING INPUT','WAITING DEPENDENCY','NEEDS DECISION','DONE']);
const VALID_EFFORT = new Set(['UNKNOWN','XS','S','M','L','XL']);
const MAX_NOTE=20000, MAX_BODY=50000, MAX_EMAIL=2000;
const MAX_TASKS=100;
const MAX_PAYLOAD_BYTES=3*1024*1024;

function sanitizeDraft(entry) {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry) ||
      !VALID_STATUS.has(entry.manualStatus) ||
      !VALID_EFFORT.has(entry.manualEffort || 'UNKNOWN') ||
      typeof entry.note !== 'string' || entry.note.length > MAX_NOTE) return null;
  const mail = entry.emailDraft;
  if (!mail || typeof mail !== 'object' || Array.isArray(mail) ||
      typeof mail.to !== 'string' || mail.to.length > MAX_EMAIL ||
      typeof mail.subject !== 'string' || mail.subject.length > MAX_EMAIL ||
      typeof mail.body !== 'string' || mail.body.length > MAX_BODY) return null;
  const changedAt = typeof entry.changedAt === 'string' &&
    Number.isFinite(Date.parse(entry.changedAt)) ? entry.changedAt : null;
  return {manualStatus:entry.manualStatus,manualEffort:entry.manualEffort || 'UNKNOWN',
    note:entry.note,emailDraft:{to:mail.to,subject:mail.subject,body:mail.body},
    changedAt,baseRevision:Number.isSafeInteger(entry.baseRevision) && entry.baseRevision>=0 ?
      entry.baseRevision : null};
}
export function sanitizeDraftMap(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const result={};
  for(const [key,entry] of Object.entries(value).slice(0,MAX_TASKS))
    if (ISSUE.test(key)) {
      const cleaned=sanitizeDraft(entry);
      if (cleaned) result[key]=cleaned;
    }
  return result;
}

function parseRecord(raw) {
  if (!raw || raw.length > MAX_PAYLOAD_BYTES) return null;
  try {
    const record=JSON.parse(raw);
    if (record?.version!==3 || typeof record.savedAt !== 'string' ||
        !Number.isFinite(Date.parse(record.savedAt))) return null;
    return {savedAt:record.savedAt,forms:sanitizeDraftMap(record.forms)};
  } catch {return null;}
}
const bytes=value=>new TextEncoder().encode(value).length;

export function createDraftRecoveryStore({local,session,newId,now=()=>Date.now()}) {
  let id=null,error=null;
  try {
    const saved=session.getItem(TAB_ID_KEY);
    id=TAB.test(saved||'') ? saved : newId();
    if (!TAB.test(id)) throw Error('Missing secure tab ID');
    session.setItem(TAB_ID_KEY,id);
  } catch {error='STORAGE_DENIED';id=null;}
  const ownKey=()=>id ? RECORD_PREFIX+id : null;

  function load() {
    if (!id) return {};
    try {
      const existing=parseRecord(local.getItem(ownKey()));
      if(existing) return existing.forms;
      // Legacy shared storage: copy before deleting, and only in the tab
      // which successfully persisted its own new copy. Other tabs may still
      // run the previous release; future edits cannot overwrite this copy.
      const legacy=local.getItem(LEGACY_DRAFT_KEY);
      if (!legacy || legacy.length>MAX_PAYLOAD_BYTES) return {};
      const legacyData=JSON.parse(legacy);
      if (legacyData && typeof legacyData === 'object' && !Array.isArray(legacyData) &&
          Object.keys(legacyData).length > MAX_TASKS) {
        // Never migrate just the first 100 then delete the sole legacy copy.
        error='CAPACITY_EXCEEDED';return {};
      }
      const forms=sanitizeDraftMap(legacyData);
      if(Object.keys(forms).length && persist(forms)) local.removeItem(LEGACY_DRAFT_KEY);
      return forms;
    } catch {error='READ_FAILED';return {};}
  }
  function persist(forms) {
    if(!id) {error='STORAGE_DENIED';return false;}
    try {
      if (!forms || typeof forms !== 'object' || Array.isArray(forms) ||
          Object.keys(forms).length > MAX_TASKS) {
        error='CAPACITY_EXCEEDED';return false;
      }
      const validated=sanitizeDraftMap(forms);
      const serialized=JSON.stringify({version:3,savedAt:new Date(now()).toISOString(),forms:validated});
      if (bytes(serialized)>MAX_PAYLOAD_BYTES) {
        error='CAPACITY_EXCEEDED';return false;
      }
      if(Object.keys(validated).length) local.setItem(ownKey(),serialized);
      else local.removeItem(ownKey());
      error=null;
      return true;
    } catch {error='WRITE_FAILED';return false;}
  }
  function others() {
    const result=[];
    if(!id)return result;
    try {
      for(let index=0;index<local.length;index++) {
        const key=local.key(index);
        if(!key?.startsWith(RECORD_PREFIX) || key===ownKey()) continue;
        const otherId=key.slice(RECORD_PREFIX.length);
        if(!TAB.test(otherId)) continue;
        const parsed=parseRecord(local.getItem(key));
        if(!parsed || !Object.keys(parsed.forms).length) continue;
        const ageDays=Math.max(0,Math.floor((now()-Date.parse(parsed.savedAt))/86400000));
        result.push({id:otherId,savedAt:parsed.savedAt,ageDays,
          count:Object.keys(parsed.forms).length,stale:ageDays>=RETENTION_DAYS});
      }
    } catch {error='READ_FAILED';}
    return result.sort((a,b)=>b.savedAt.localeCompare(a.savedAt));
  }
  function adopt(otherId,current={},occupied=[]) {
    if(!id || !TAB.test(otherId) || otherId===id) return {added:{},skipped:[]};
    try {
      const parsed=parseRecord(local.getItem(RECORD_PREFIX+otherId));
      if(!parsed)return {added:{},skipped:[]};
      const protectedKeys=new Set([...Object.keys(current),...occupied]);
      const added={},skipped=[];
      for (const [key,value] of Object.entries(parsed.forms))
        if(protectedKeys.has(key)) skipped.push(key);
        else added[key]=value;
      if(Object.keys(added).length && !persist({...current,...added}))
        return {added:{},skipped:Object.keys(parsed.forms),failed:true};
      // NEVER remove another tab's copy or overwrite its unsaved forms.
      return {added,skipped};
    } catch {error='READ_FAILED';return {added:{},skipped:[],failed:true};}
  }
  function rotateTabId() {
    if (!id) return false;
    const previousId=id;
    try {
      const next=newId();
      if (!TAB.test(next) || next===id) return false;
      const existing=parseRecord(local.getItem(ownKey()));
      session.setItem(TAB_ID_KEY,next);
      id=next;
      if (existing && !persist(existing.forms)) {
        id=previousId;
        session.setItem(TAB_ID_KEY,previousId);
        return false;
      }
      return true;
    } catch {error='WRITE_FAILED';return false;}
  }
  function clearExpired() {
    const expired=others().filter(x=>x.stale);
    let cleared=0;
    try {
      for (const entry of expired) {
        local.removeItem(RECORD_PREFIX+entry.id);
        cleared++;
      }
    } catch {error='WRITE_FAILED';}
    return {cleared,remaining:expired.length-cleared};
  }
  return {ownKey,load,persist,others,adopt,rotateTabId,clearExpired,
    get id(){return id;},get error(){return error;}};
}
