// Explicitly opt-in local-only metrics page. One initial request and manual refresh.
// No timers, localStorage, cookies, network beacons, dynamic HTML or remote URLs.
const $ = id => document.getElementById(id);
export function describeMetrics(data) {
  if (!data || data.localOnly !== true || data.remoteTelemetry !== false) {
    throw new Error('Local-only metrics contract missing');
  }
  const n = value => Number.isFinite(value) ? String(value) : '—';
  return {
    total:n(data.sampledApiResponses), failures:n(data.server5xx),
    client:n(data.client4xx), rate:n(data.successPercent)+'%',
    remaining:n(data.errorBudgetRemaining),
    latency:n(data.responseLatencyP95Ms)+' ms',
    state:data.insufficientSamples
      ? 'Недостатньо даних для надійного висновку (менше 100 відповідей).'
      : data.sampleTruncated
        ? 'Ліміт вибірки досягнуто, показники можуть бути неповними.'
        : 'Лічильники лише поточної сесії, за останні 60 хвилин.'
  };
}
export async function refreshBudget(fetcher=fetch) {
  const response=await fetcher('/api/error-budget',{cache:'no-store'});
  if (!response.ok) throw new Error('Metrics route unavailable');
  const fields=describeMetrics(await response.json());
  for (const [id,value] of Object.entries(fields)) {
    if (id==='state') $('budgetState').textContent=value;
    else $(id).textContent=value;
  }
}
const button=$('refreshBudget');
if (button) {
  button.addEventListener('click',()=>{
    refreshBudget().catch(()=>{$('budgetState').textContent='Не вдалося завантажити локальні лічильники.';});
  });
  refreshBudget().catch(()=>{$('budgetState').textContent='Не вдалося завантажити локальні лічильники.';});
}
