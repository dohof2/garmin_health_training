import assert from 'node:assert/strict';
import {after,test} from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
after(()=>server.close());
const {default:TrainingWeek}=await server.ssrLoadModule('/src/TrainingWeek.tsx');
const {mergeWorkoutStatus}=await server.ssrLoadModule('/src/trainingCalendar.ts');
const ride=(id,status,sport='cycling')=>({id,title:`Fictional ${sport} session ${id}`,sport,completion_status:status,scheduled_for:'2026-10-27T08:00:00Z',definition:{scheduled_date:'2026-10-27',time_unspecified:true,duration_minutes:60}});
const render=workouts=>renderToStaticMarkup(createElement(TrainingWeek,{workouts,timezone:'Asia/Jerusalem',selectedWorkoutId:null,onSelect:()=>{},now:new Date('2026-10-27T10:00:00Z')}));

test('completed session reappears beside a remaining session without marking the entire day done',()=>{
 const workouts=mergeWorkoutStatus([ride('done','planned'),ride('remaining','planned','strength')],[ride('done','completed')]);
 const html=render(workouts);
 assert.equal(workouts.length,2);
 assert.equal((html.match(/workout-day--completed/g)||[]).length,1);
 assert.match(html,/1 of 2 sessions completed/);
 assert.doesNotMatch(html,/All sessions completed/);
 assert.match(html,/workout-completion-icon/);
 assert.match(html,/>Completed<\/span>/);
 assert.match(html,/Fictional strength session remaining/);
});
test('all completed days have a labelled checkmark and no rest placeholder',()=>{
 const html=render([ride('done','completed')]);
 const today=html.split('class="training-day-card"')[1];
 assert.match(today,/All sessions completed/);
 assert.match(today,/Completed/);
 assert.doesNotMatch(today,/Rest day/);
 assert.match(today,/aria-expanded="false" aria-controls="selected-workout-detail"/);
 assert.match(today,/aria-hidden="true"/);
});
test('refresh merging deduplicates IDs, ignores canceled entries and keeps completed status',()=>{
 const a=ride('done','completed'),b=ride('later','planned');
 assert.deepEqual(mergeWorkoutStatus([a,b,ride('removed','cancelled')],[ride('done','planned')]),[a,b]);
 assert.deepEqual(mergeWorkoutStatus([b,a],[a]),[b,a]);
});

test('variant labels and upcoming mix describe actual planned cycling rather than completed or strength sessions',async()=>{
 const {default:Mix}=await server.ssrLoadModule('/src/CyclingMixSummary.tsx');
 const completed=ride('done','completed');completed.definition.workout_kind='sprint';
 const planned=ride('next','planned');planned.definition.workout_kind='endurance';planned.definition.variant_label='Comfortable continuous base';
 const strength=ride('strength','planned','strength');
 const card=render([planned]);
 assert.match(card,/Comfortable continuous base/);
 const html=renderToStaticMarkup(createElement(Mix,{sessions:[completed,planned,strength],mix:{focus:'sustained_power',quality_session_limit:1,quality_session_weights:{threshold:2,sprint:1},rotation_length:3,note:'Fictional mix'}}));
 const actual=html.split('Currently scheduled:</strong>')[1].split('</p>')[0];
 assert.match(actual,/Endurance: 1/);
 assert.doesNotMatch(actual,/Sprint: 1|strength/);
});
