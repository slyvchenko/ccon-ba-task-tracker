// Read-only transport recovery for the existing 5s revision poll.
// POST/manual operations are intentionally NEVER replayed after failures.
export function createReconnectPolicy({baseMs=5000,maxMs=60000,clock=()=>Date.now()}={}) {
  if (!Number.isFinite(baseMs) || baseMs<1 || maxMs<baseMs)
    throw Error('Invalid reconnection interval');
  let failures=0,nextAt=0,offline=false;
  return {
    shouldPoll({force=false}={}) {return force || !offline || clock()>=nextAt;},
    failed() {
      failures++;
      offline=true;
      // First retry after base delay; then exponential backoff.
      const delay=Math.min(maxMs,baseMs*Math.pow(2,Math.min(failures-1,20)));
      nextAt=clock()+delay;
      return {firstFailure:failures===1,failures,delay};
    },
    recovered() {
      const wasOffline=offline;
      failures=0;nextAt=0;offline=false;
      return wasOffline;
    },
    get offline(){return offline;},
    get failures(){return failures;}
  };
}
