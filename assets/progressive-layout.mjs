export function advancedFilterSummary({signal='all',sprint='all'}={}){
  const used=[signal!=='all',sprint!=='all'].filter(Boolean).length;
  return used ? ' · '+used+' активн'+(used===1?'ий':'і') : '';
}
export function evidenceSectionLabel(count=0) {
  return count>0 ? 'Джерела оцінки ('+count+')' : 'Джерела оцінки (не додані)';
}
