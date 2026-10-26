// Candidate scaffolds only. Never infer supplier, source, PNR, method or outcome.
// A template is never a verified BA analysis or a Jira change.
export const CANDIDATE_TEMPLATES = Object.freeze([
  Object.freeze({id:'clarify',label:'Уточнити вимоги',
    text:'Мета: [сформулювати проблему після перевірки Jira]\nДжерело: [посилання на фактичне джерело]\nНевідоме: [питання, яке потрібно підтвердити]\nНаступна дія: [хто і що перевірить]\nКритерій: [спостережуваний результат після підтвердження]'}),
  Object.freeze({id:'reproduce',label:'Перевірити помилку',
    text:'Контекст: [підтверджена версія/середовище]\nДжерело: [посилання на лог або запит, без вигаданих ID]\nКроки: [відтворені кроки]\nФактичний результат: [лише спостереження]\nОчікуваний результат: [підтверджена вимога]\nВідкриті питання: [невідомі умови]'}),
  Object.freeze({id:'handoff',label:'Передати на перевірку',
    text:'Мета передачі: [підтверджена задача]\nДокази: [посилання на джерела]\nЗроблено: [лише реально виконані дії]\nПотрібно від: [конкретний власник або питання]\nУмови приймання: [що перевірити]\nРизики/невідоме: [що ще не доведено]'})
]);

export function candidateTemplate(id) {
  return CANDIDATE_TEMPLATES.find(item=>item.id===id) || null;
}
export function candidateTemplateFor(task,id) {
  if (!task || task.active===false || task.manualStatus==='DONE') return null;
  const template=candidateTemplate(id);
  if (!template) return null;
  return {id:template.id,label:template.label,text:template.text,
    state:'UNVERIFIED_PLACEHOLDERS',
    notice:'Лише порожній каркас. Заповни факти з Jira/логів, перевір джерела й передай вручну.'};
}
