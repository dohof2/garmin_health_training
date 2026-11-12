import assert from 'node:assert/strict';
import {mkdir,mkdtemp,rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {rolldown} from 'rolldown';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const root=fileURLToPath(new URL('../',import.meta.url));
await mkdir(`${root}node_modules/.cache`,{recursive:true});
const tmp=await mkdtemp(`${root}node_modules/.cache/activity-visuals-`);
try {
 const build=await rolldown({input:{routeMetrics:`${root}src/routeMetrics.ts`,exerciseMuscles:`${root}src/exerciseMuscles.ts`,MuscleDiagram:`${root}src/MuscleDiagram.tsx`,WorkoutMuscles:`${root}src/WorkoutMuscles.tsx`},platform:'node',external:['react','react/jsx-runtime'],transform:{jsx:'react-jsx'}});
 await build.write({dir:tmp,format:'esm'});await build.close();
 const {chooseMetric,metricValue,routeColour,powerScale,powerColour}=await import(`${tmp}/routeMetrics.js`);
 const data={available_metrics:['power_watts','speed_mps'],default_metric:'power_watts'};
 assert.equal(chooseMetric(data,null),'power_watts');assert.equal(chooseMetric(data,'speed_mps'),'speed_mps');
 assert.equal(chooseMetric({available_metrics:['speed_mps'],default_metric:'speed_mps'},'power_watts'),'speed_mps');
 assert.equal(metricValue('speed_mps',10,'km'),'36.0 km/h');assert.equal(metricValue('power_watts',220,'mi'),'220 W');
 assert.equal(routeColour(null,0,100),'#89929c');assert.notEqual(routeColour(0,0,100),routeColour(100,0,100));
 const bands=powerScale([0,...Array.from({length:100},(_,i)=>100+i),1200]);
 assert.ok(new Set([110,130,150,170,190].map(v=>powerColour(v,bands))).size>=5);
 assert.equal(powerColour(0,bands),'hsl(220.000, 85%, 46%)');
 assert.notEqual(powerColour(120,bands),powerColour(121,bands));
 assert.notEqual(powerColour(121,bands),powerColour(122,bands));assert.equal(powerColour(null,bands),'#89929c');
 const {muscleProfile,exerciseMuscles,combinedMuscles}=await import(`${tmp}/exerciseMuscles.js`);
 assert.deepEqual(muscleProfile('calf_raise').primary,['calves']);
 assert.deepEqual(muscleProfile(undefined,'Pull-up'),muscleProfile('pullup_progression'));
 const combined=combinedMuscles([{id:'air_squat',name:'Air Squat'},{id:'dead_bug',name:'Dead Bug'}]);
 assert.ok(combined.primary.includes('abs'));assert.ok(!combined.secondary.includes('abs'));
 assert.ok(combined.primary.includes('glutes'));
 assert.equal(muscleProfile('unknown','Unreviewed exercise'),undefined);
 for(const profile of Object.values(exerciseMuscles)) { assert.ok(profile.primary.length);assert.ok(!profile.primary.some(m=>profile.secondary.includes(m))); }
 const {default:Diagram}=await import(`${tmp}/MuscleDiagram.js`);
 const html=renderToStaticMarkup(createElement(Diagram,{exerciseId:'air_squat',name:'Air Squat'}));
 assert.match(html,/Front/);assert.match(html,/Back/);assert.match(html,/#e84949/);assert.match(html,/#f3cd43/);assert.match(html,/Quadriceps/);
 const {default:WorkoutMuscles}=await import(`${tmp}/WorkoutMuscles.js`);
 const unsupported=renderToStaticMarkup(createElement(WorkoutMuscles,{exercises:[{name:'Squat · variation not specified'},{name:'Unrecognized 12345 variation'}]}));
 assert.match(unsupported,/Not included in the illustration/);assert.match(unsupported,/Unrecognized 12345/);
 console.log('Passed: power/speed defaults and preference fallback, units, missing-data colour, muscle mappings, accessible front/back diagrams.');
} finally { await rm(tmp,{recursive:true,force:true}); }
