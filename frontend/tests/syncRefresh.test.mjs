import assert from 'node:assert/strict';
import {after,test} from 'node:test';
import {createServer} from 'vite';
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
after(()=>server.close());
const {refreshReadViews,committedSyncRevision}=await server.ssrLoadModule('/src/syncRefresh.ts');

test('view invalidation precedes reads and successful fields survive one failure',async()=>{
 let invalidated=false;const calls=[];
 const result=await refreshReadViews({summary:'/summary',weeklyCalories:'/weekly',syncStatus:'/status'},()=>{invalidated=true;},async url=>{
  assert.equal(invalidated,true);calls.push(url);
  if(url==='/weekly')throw Error('unavailable');
  return url==='/summary'?{activity_count:4}:{last_job:{status:'completed'}};
 });
 assert.equal(calls.length,3);assert.equal(result.patch.summary.activity_count,4);
 assert.equal(result.patch.syncStatus.last_job.status,'completed');assert.equal('weeklyCalories' in result.patch,false);
 assert.match(result.warning,/weeklyCalories/);
});
test('complete refresh preserves nullable values without a warning',async()=>{
 let revisions=0;
 const result=await refreshReadViews({weeklyCalories:'/weekly'},()=>{revisions++;},async()=>null);
 assert.equal(revisions,1);assert.deepEqual(result.patch,{weeklyCalories:null});assert.equal(result.warning,'');
});
test('new load commit refreshes the view even while sync interval progress is unchanged',()=>{
 const job={id:'sync-a',progress_current:3,checkpoint:{data_revision:3}};
 const before=committedSyncRevision(job);
 assert.equal(committedSyncRevision({...job}),before);
 assert.notEqual(committedSyncRevision({...job,checkpoint:{data_revision:4}}),before);
 assert.notEqual(committedSyncRevision({...job,id:'sync-b'}),before);
 assert.equal(committedSyncRevision(null),null);
 assert.equal(committedSyncRevision({id:'older-server',progress_current:3}),'older-server:3');
});

const {syncViewRevision,watchSyncStatus}=await server.ssrLoadModule('/src/syncRefresh.ts');
test('terminal status refreshes cards even with no new interval commit',()=>{
 const job={id:'sync-a',checkpoint:{data_revision:9},status:'running'};
 assert.notEqual(syncViewRevision(job),syncViewRevision({...job,status:'completed',finished_at:'2026-10-30T07:59:00Z'}));
 assert.notEqual(syncViewRevision(job),syncViewRevision({...job,status:'failed'}));
 assert.equal(syncViewRevision(null),null);
});
test('plots wait for a terminal sync status through every progress update',()=>{
 for(const revision of [0,1,5,20]) {
  assert.equal(syncViewRevision({id:'a',status:'running',checkpoint:{data_revision:revision}}),null);
 }
 for(const status of ['completed','failed']) {
  const job={id:'a',status,finished_at:'2026-11-01T10:00:00Z'};
  assert.ok(syncViewRevision(job));
  assert.equal(syncViewRevision({...job,checkpoint:{data_revision:1}}),syncViewRevision({...job,checkpoint:{data_revision:20}}));
 }
});
test('idle watcher detects a sync started elsewhere, progress and completion',async()=>{
 const timers=[],seen=[];let reads=0;
 const states=[{last_job:{id:'a',status:'completed'}},{last_job:{id:'b',status:'running',checkpoint:{data_revision:0}}},{last_job:{id:'b',status:'running',checkpoint:{data_revision:1}}},{last_job:{id:'b',status:'completed'}}];
 const monitor=watchSyncStatus({load:async()=>states[reads++],onStatus:s=>seen.push(s),schedule:(fn,delay)=>{timers.push({fn,delay});return timers.length;},cancel:()=>{}});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(timers.at(-1).delay,10000);
 for(let i=0;i<3;i++){timers.at(-1).fn();await new Promise(resolve=>setImmediate(resolve));}
 assert.deepEqual(seen,states);assert.equal(timers[1].delay,2000);assert.equal(timers.at(-1).delay,10000);
 monitor.stop();
});
test('hidden windows defer reads, focus catches up and stop ignores in-flight output',async()=>{
 let visible=false,reads=0,deliveries=0,release;
 const timers=[];
 const monitor=watchSyncStatus({load:()=>{reads++;return new Promise(resolve=>{release=resolve;});},onStatus:()=>deliveries++,isVisible:()=>visible,schedule:(fn,delay)=>{timers.push({fn,delay});return timers.length;},cancel:()=>{}});
 assert.equal(reads,0);visible=true;monitor.wake();assert.equal(reads,1);
 monitor.wake();assert.equal(reads,1);monitor.stop();release({last_job:{status:'completed'}});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(deliveries,0);
});
