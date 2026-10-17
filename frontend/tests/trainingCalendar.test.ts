import assert from 'node:assert/strict';
import {test} from 'node:test';
import {trainingDate,trainingWeek} from '../src/trainingCalendar.ts';

test('Jerusalem spring DST retains seven consecutive local calendar dates',()=>{
  assert.deepEqual(trainingWeek(new Date('2026-03-26T22:30:00Z'),'Asia/Jerusalem'),['2026-03-27','2026-03-28','2026-03-29','2026-03-30','2026-03-31','2026-04-01','2026-04-02']);
});
test('Jerusalem autumn DST retains seven dates including repeated hour',()=>{
  assert.deepEqual(trainingWeek(new Date('2026-10-24T23:30:00Z'),'Asia/Jerusalem'),['2026-10-25','2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30','2026-10-31']);
  assert.equal(trainingDate(new Date('2026-10-24T22:30:00Z'),'Asia/Jerusalem'),trainingDate(new Date('2026-10-24T23:30:00Z'),'Asia/Jerusalem'));
});
test('local midnight and year boundary use selected timezone rather than UTC',()=>{
  assert.equal(trainingDate(new Date('2026-12-31T22:30:00Z'),'Asia/Jerusalem'),'2027-01-01');
  assert.equal(trainingWeek(new Date('2027-01-01T00:30:00Z'),'America/Los_Angeles')[0],'2026-12-31');
});

test('date-only workout labels never show an internal anchor clock',async()=>{
  const {workoutDate,workoutLabel}=await import('../src/trainingCalendar.ts');
  const workout={scheduled_for:'2026-10-17T09:00:00Z',definition:{time_unspecified:true,scheduled_date:'2026-10-17'}};
  assert.equal(workoutDate(workout,'America/Los_Angeles'),'2026-10-17');
  assert.doesNotMatch(workoutLabel(workout,'Asia/Jerusalem'),/\d{1,2}:\d{2}/);
  assert.doesNotMatch(workoutLabel(workout,'America/Los_Angeles'),/\d{1,2}:\d{2}/);
});
test('explicit workout clock still appears and top-level date-only metadata is supported',async()=>{
  const {workoutDate,workoutLabel}=await import('../src/trainingCalendar.ts');
  assert.match(workoutLabel({scheduled_for:'2026-10-17T05:00:00Z'},'Asia/Jerusalem'),/\d{1,2}:\d{2}/);
  const workout={scheduled_for:'2026-10-17T00:00:00Z',scheduled_date:'2026-10-18',time_unspecified:true};
  assert.equal(workoutDate(workout,'Asia/Jerusalem'),'2026-10-18');
  assert.doesNotMatch(workoutLabel(workout,'Asia/Jerusalem'),/\d{1,2}:\d{2}/);
});
