import assert from 'node:assert/strict';
import {coalescedFetch} from '../src/request.ts';
let calls=[];
globalThis.fetch=(url,options={})=>new Promise((resolve,reject)=>{const call={url,options,resolve:()=>resolve(new Response(JSON.stringify({url}),{headers:{'Content-Type':'application/json'}}))};calls.push(call);options.signal?.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')));});
const first=new AbortController(),second=new AbortController();
const a=coalescedFetch('/api/test',{signal:first.signal}),b=coalescedFetch('/api/test',{signal:second.signal});
assert.equal(calls.length,1);const abortCheck=assert.rejects(a,{name:'AbortError'});first.abort();await abortCheck;
assert.equal(calls[0].options.signal.aborted,false);calls[0].resolve();assert.deepEqual(await (await b).json(),{url:'/api/test'});
const c=coalescedFetch('/api/test');assert.equal(calls.length,2);calls[1].resolve();await c;
const d=coalescedFetch('/api/write',{method:'POST'}),e=coalescedFetch('/api/write',{method:'POST'});assert.equal(calls.length,4);calls[2].resolve();calls[3].resolve();await Promise.all([d,e]);
const f=coalescedFetch('/api/charts/query',{method:'POST',body:'one'}),g=coalescedFetch('/api/charts/query',{method:'POST',body:'one'}),h=coalescedFetch('/api/charts/query',{method:'POST',body:'two'});assert.equal(calls.length,6);calls[4].resolve();calls[5].resolve();await Promise.all([f,g,h]);
const last=new AbortController();const i=coalescedFetch('/api/cancel',{signal:last.signal});const rejection=assert.rejects(i,{name:'AbortError'});last.abort();await rejection;await new Promise(resolve=>queueMicrotask(resolve));assert.equal(calls[6].options.signal.aborted,true);
console.log('Shared reads, independent cancellation, fresh repeat reads and unshared writes passed.');

const oldRead=coalescedFetch('/api/freshness'),write=coalescedFetch('/api/save',{method:'POST'});const readCall=calls.at(-2),writeCall=calls.at(-1);writeCall.resolve();await write;const freshRead=coalescedFetch('/api/freshness');assert.notEqual(calls.at(-1),readCall);calls.at(-1).resolve();readCall.resolve();await Promise.all([oldRead,freshRead]);console.log('Successful writes invalidate pre-write in-flight reads.');
