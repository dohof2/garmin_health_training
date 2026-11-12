import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { rolldown } from 'rolldown';

const root = fileURLToPath(new URL('../', import.meta.url));
await mkdir(`${root}node_modules/.cache`, { recursive: true });
const temporary = await mkdtemp(`${root}node_modules/.cache/journal-availability-`);
try {
  const build = await rolldown({ input: {journalAvailability: `${root}src/journalAvailability.ts`, ReadinessCard: `${root}src/ReadinessCard.tsx`, recentActivitySummary: `${root}src/recentActivitySummary.ts`}, platform: 'node', external: ['react','react/jsx-runtime'], transform: {jsx:'react-jsx'} });
  await build.write({ dir: temporary, format: 'esm' });
  await build.close();
  const { availabilityRequest } = await import(`${temporary}/journalAvailability.js`);
  const { readinessTime } = await import(`${temporary}/ReadinessCard.js`);
  const {sevenDayRange,summarizeActivities,allRecentActivities,ridingTime}=await import(`${temporary}/recentActivitySummary.js`);
  const range=sevenDayRange('2026-11-10');
  assert.deepEqual(range,{start:'2026-11-04',end:'2026-11-10'});
  assert.deepEqual(sevenDayRange('2026-11-02'),{start:'2026-10-27',end:'2026-11-02'});
  const activity=(id,type,day,seconds=3600,meters=10000)=>({id,activity_type:type,local_date:day,duration_seconds:seconds,distance_meters:meters});
  const ride=activity('ride','mountain_biking','2026-11-04');
  const summary=summarizeActivities([ride,ride,activity('indoor','virtual_ride','2026-11-10',1800,5000),activity('missing','indoor_cycling','2026-11-09',null,null),activity('strength','strength_training','2026-11-08'),activity('weight','weight_training','2026-11-07'),activity('old','cycling','2026-11-03'),activity('future','cycling','2026-11-11')],range);
  assert.deepEqual(summary,{strength:2,rides:3,ridingSeconds:5400,ridingKm:15,missingTime:1,missingDistance:1});
  assert.equal(ridingTime(summary.ridingSeconds),'1h 30m');
  assert.deepEqual(summarizeActivities([activity('unknown','cycling','2026-11-10',null,null)],range),{strength:0,rides:1,ridingSeconds:null,ridingKm:null,missingTime:1,missingDistance:1});
  assert.equal(summarizeActivities([],range).ridingKm,0);
  assert.equal(summarizeActivities([activity('zero','cycling','2026-11-10',0,0)],range).missingTime,0);
  const page=Array.from({length:100},(_,i)=>activity(String(i),'cycling','2026-11-10'));
  const offsets=[];
  const collected=await allRecentActivities(async offset=>{offsets.push(offset);return offset===0?page:[page[99],activity('last','cycling','2026-11-10')];});
  assert.deepEqual(offsets,[0,100]);assert.equal(collected.length,101);
  await assert.rejects(()=>allRecentActivities(async offset=>{if(offset===0)return page;throw new Error('Page failed');}),/Page failed/);

  const expectedTime = new Date('2026-11-10T07:00:00Z').toLocaleTimeString([], {timeZone:'Asia/Jerusalem',hour:'2-digit',minute:'2-digit'});
  for (const value of ['2026-11-10 07:00:00','2026-11-10T07:00:00Z','2026-11-10T09:00:00+02:00']) assert.equal(readinessTime(value,'Asia/Jerusalem'),expectedTime);
  assert.equal(readinessTime('invalid','Asia/Jerusalem'),'Time unavailable');
  const monday = { weekday: 0, mode: 'training', total_limit_minutes: null, activities: [{ slot_id: 'bike', sport: 'cycling', min_minutes: 60, max_minutes: 90 }] };
  const tuesday = { weekday: 1, mode: 'rest', total_limit_minutes: null, activities: [] };
  const sunday = { weekday: 6, mode: 'rest', total_limit_minutes: null, activities: [] };
  const context = { revision: 7, answers: { week_schedule: [sunday, monday, tuesday], sports: ['cycling', 'strength'], equipment: ['bike'], pain_or_illness: false, weekly_caps: { cycling: { max_minutes: 300 } }, availability: [], weekly_minutes: {} } };
  const before = structuredClone(context);
  const change = { ...tuesday, mode: 'training', activities: [{ slot_id: 'strength', sport: 'strength', min_minutes: null, max_minutes: 60 }] };
  const request = availabilityRequest(context, change, 7);
  assert.equal(request.expected_revision, 7);
  assert.deepEqual(request.answers.week_schedule, [monday, change, sunday]);
  for (const field of ['sports', 'equipment', 'pain_or_illness', 'weekly_caps']) assert.deepEqual(request.answers[field], before.answers[field]);
  assert.equal('availability' in request.answers, false);
  assert.equal('weekly_minutes' in request.answers, false);
  assert.deepEqual(context, before, 'Preparing a save must not mutate the loaded preferences');
  assert.throws(() => availabilityRequest({ ...context, revision: 8 }, change, 7), /changed while you were editing/);
  assert.throws(() => availabilityRequest(context, change, undefined), /changed while you were editing/);
  assert.deepEqual(context, before, 'Rejected stale edits must leave loaded preferences unchanged');
  console.log('Passed: seven-day bounds, sport counts, riding totals, missing values, deduplication and pagination; preference guards and readiness UTC times.');
} finally {
  await rm(temporary, { recursive: true, force: true });
}
