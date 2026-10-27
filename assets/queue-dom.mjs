// Reconcile only unchanged-key queue nodes; do not virtualize rows out of the
// accessibility tree or remove the traditional list/detail layout.
// The queue uses delegated click handling, so replacement does not lose handlers.
export function queuePatchIndexes(previous, next) {
  if (!previous || previous.length !== next.length) return null;
  for (let i=0;i<next.length;i++) {
    if (previous[i].id !== next[i].id) return null;
  }
  const indexes=[];
  for(let i=0;i<next.length;i++) if(previous[i].html!==next[i].html) indexes.push(i);
  return indexes;
}
export function invalidateQueueEntry(previous,key) {
  if (!previous) return false;
  const row=previous.find(item=>item.id==='task:'+key);
  if (!row) return false;
  // An inline dirtiness mutation is not represented by the cached row HTML.
  // Force only this one row to reconcile on the next render.
  row.html=null;
  return true;
}
export function createQueueDomRenderer() {
  let previous=null;
  return {
    invalidateRow(key) { return invalidateQueueEntry(previous,key); },
    render(list, entries) {
      const changed=queuePatchIndexes(previous,entries);
      if (changed===null || list.children.length!==entries.length) {
        list.innerHTML=entries.map(x=>x.html).join('');
      } else if(changed.length) {
        const template=list.ownerDocument.createElement('template');
        for(const index of changed) {
          template.innerHTML=entries[index].html;
          const replacement=template.content.firstElementChild;
          if (!replacement) throw Error('Queue row markup must contain one element.');
          list.children[index].replaceWith(replacement);
        }
      }
      previous=entries.map(({id,html})=>({id,html}));
      return changed===null?'rebuild':changed.length?'patch':'unchanged';
    }
  };
}
