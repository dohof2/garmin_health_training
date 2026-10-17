import test from 'node:test';
import assert from 'node:assert/strict';
import {candidatePreferences,sameCandidate} from '../src/trainingCandidate.ts';

const saved={sports:['cycling'],availability:[{weekday:0,start_time:'08:00',minutes:60}],weekly_minutes:{cycling:180}};
test('partial sport-only preview preserves safe editable fields without mutation',()=>{
  const patch={sports:['cycling','strength']};
  const display=candidatePreferences(saved,patch);
  assert.equal(display.weekly_minutes.cycling,180);
  assert.equal(display.weekly_minutes.strength,undefined);
  assert.equal(display.availability[0].start_time,'08:00');
  assert.deepEqual(patch,{sports:['cycling','strength']});
  assert.deepEqual(saved.sports,['cycling']);
});
test('empty saved setup and incomplete preview can render every sport and day',()=>{
  const display=candidatePreferences({sports:[],availability:[],weekly_minutes:{}},{sports:['cycling']});
  for(const sport of ['cycling','running','strength'])assert.equal(display.weekly_minutes[sport]??0,0);
  assert.equal(display.availability.find(slot=>slot.weekday===0),undefined);
});
test('explicit empty candidate arrays and individual sport budgets are retained',()=>{
  const display=candidatePreferences(saved,{sports:[],availability:[],weekly_minutes:{strength:60}});
  assert.deepEqual(display.sports,[]);assert.deepEqual(display.availability,[]);
  assert.deepEqual(display.weekly_minutes,{cycling:180,strength:60});
});
test('approval comparison ignores object key order but detects changed workout content',()=>{
  assert.equal(sameCandidate({brief:{goal:'ftp',horizon_weeks:16},candidate_answers:{sports:['cycling'],weekly_minutes:{cycling:180}}},{candidate_answers:{weekly_minutes:{cycling:180},sports:['cycling']},brief:{horizon_weeks:16,goal:'ftp'}}),true);
  assert.equal(sameCandidate({sessions:[{minutes:60}]},{sessions:[{minutes:90}]}),false);
  assert.equal(sameCandidate({sports:['cycling','strength']},{sports:['strength','cycling']}),false);
});
