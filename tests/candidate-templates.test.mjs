import test from 'node:test';
import assert from 'node:assert/strict';
import {CANDIDATE_TEMPLATES,candidateTemplateFor} from '../assets/candidate-templates.mjs';
test('candidate templates are explicit and unverified',()=>{
  assert.equal(CANDIDATE_TEMPLATES.length,3);
  const item=candidateTemplateFor({active:true,manualStatus:'AUTO'},'clarify');
  assert.equal(item.state,'UNVERIFIED_PLACEHOLDERS');
  assert.match(item.text,/Джерело/);
});
