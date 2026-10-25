// Cache only data derived from the current immutable Jira snapshot objects.
// The caller MUST invalidate on in-place manual status/score changes.
import {rankTasks,filterTasks} from './task-rules.mjs';

export function createQueueModel() {
  let source = null, ranked = [], filteredSource = null, filteredKey = '',
      filtered = [], revision = 0, index = new WeakMap();
  const stats = {rankingBuilds:0,filterBuilds:0,indexBuilds:0};

  function searchText(task) {
    if (index.has(task)) return index.get(task);
    const analysis = task.analysis && typeof task.analysis === 'object' ? task.analysis : {};
    const brief = analysis.briefing || {};
    const links = (task.links || task.linkedIssues || []).map(item =>
      typeof item === 'string' ? item : (item.linkedKey || item.key || ''));
    const text = [
      task.key,task.summary,task.jiraStatus,task.priority,
      analysis.nextActionUk,analysis.standardDescription,
      brief.technicalScopeUk,brief.currentUk,brief.targetUk,
      ...(brief.rules || []).slice(0,30).flatMap(rule=>[rule.whenUk,rule.thenUk]),
      ...links,...(task.blockedBy || [])
    ].filter(value=>typeof value === 'string').join(' ').toLocaleLowerCase('uk-UA');
    const result={text,folded:text.replace(/[^\p{L}\p{N}]/gu,'')};
    index.set(task,result);
    stats.indexBuilds++;
    return result;
  }

  function rankedTasks(items) {
    if (items !== source) {
      source=items;
      ranked=rankTasks(items);
      filteredSource=null;
      index=new WeakMap();
      stats.rankingBuilds++;
    }
    return ranked;
  }

  function visibleTasks(items,filters={}) {
    const sorted=rankedTasks(items);
    const key=JSON.stringify([filters.search||'',filters.filter||'open',
      filters.signal||'all',filters.sprint||'all',revision]);
    if (filteredSource===sorted && filteredKey===key) return filtered;
    filtered=filterTasks(sorted,filters,searchText);
    filteredKey=key;
    filteredSource=sorted;
    stats.filterBuilds++;
    return filtered;
  }

  function invalidate() {
    revision++;
    source=null;
    filteredSource=null;
    index=new WeakMap();
  }

  return {rankedTasks,visibleTasks,invalidate,stats};
}

export function selectedAfterFilter(visibleItems,selected,{protectEditor=false}={}) {
  if (visibleItems.some(task=>task.key===selected)) return selected;
  if (protectEditor && selected) return selected;
  return visibleItems[0]?.key || null;
}

// Inject timer functions in tests; production uses browser timers.
export function createSearchDebouncer(callback,delay=130,schedule=setTimeout,cancelTimer=clearTimeout) {
  let timer=null;
  return {
    schedule() {
      if (timer!==null) cancelTimer(timer);
      timer=schedule(()=>{timer=null;callback();},delay);
    },
    flush() {
      if (timer===null) return false;
      cancelTimer(timer);
      timer=null;
      callback();
      return true;
    },
    cancel() {
      if (timer===null) return;
      cancelTimer(timer);
      timer=null;
    },
    pending(){return timer!==null;}
  };
}
