import assert from 'node:assert/strict';
import {test} from 'node:test';
import {displaySteps} from '../src/workoutSteps.ts';
test('nested repeated groups expose stable editable paths without changing leaf instructions',()=>{
 const steps=displaySteps([{type:'warmup',duration_seconds:600},{type:'repeat',repetitions:2,steps:[{type:'work',duration_seconds:240},{type:'recovery',duration_seconds:180}]}]);
 assert.deepEqual(steps.map(s=>s.path),['1','2.1','2.2','2.1','2.2']);
 assert.equal(steps.reduce((total,s)=>total+s.duration_seconds,0),1440);
});
test('malformed or excessively expanded structures do not render partial invented instructions',()=>{
 assert.deepEqual(displaySteps([{type:'repeat',repetitions:50,steps:[{type:'repeat',repetitions:50,steps:[{type:'work',duration_seconds:10}]}]}]),[]);
 assert.deepEqual(displaySteps([{type:'work',duration_seconds:NaN}]),[]);
});
