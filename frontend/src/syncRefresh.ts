import {invalidateReadRequests,requestJson} from './request';

export function committedSyncRevision(job:{id:string;progress_current?:number;checkpoint?:{data_revision?:number}}|null|undefined){
 if(!job)return null;
 // The commit marker also advances for the fast load fetch, which is not a
 // separate broad-sync interval. Retain compatibility with an older backend.
 return `${job.id}:${job.checkpoint?.data_revision??job.progress_current??0}`;
}

// A failed auxiliary read must not block committed chart/activity data refreshing.
export async function refreshReadViews<T extends object>(urls:{[K in keyof T]:string},invalidateViews:()=>void,load:(url:string)=>Promise<unknown>=requestJson){
 invalidateReadRequests();
 invalidateViews();
 const keys=Object.keys(urls) as (keyof T)[];
 const settled=await Promise.allSettled(keys.map(key=>load(urls[key])));
 const patch:Partial<T>={};const failed:string[]=[];
 settled.forEach((result,index)=>{
  const key=keys[index];
  if(result.status==='fulfilled')patch[key]=result.value as T[typeof key];
  else failed.push(String(key));
 });
 return {patch,warning:failed.length?`Some saved summaries could not be refreshed (${failed.join(', ')}). Charts and activities requested fresh data; retry sync to refresh the remaining summaries.`:''};
}

export function syncViewRevision(job:(NonNullable<Parameters<typeof committedSyncRevision>[0]>&{status?:string;finished_at?:string|null})|null|undefined){
 if(!job || (job.status !== 'completed' && job.status !== 'failed'))return null;
 return `${job.id}:${job.status}:${job.finished_at??''}`;
}

// Watch idle sessions too: a different tab, Telegram or the worker may start sync.
export function watchSyncStatus<T extends {last_job?:{status?:string}|null}>({load,onStatus,isVisible=()=>true,schedule=(fn,ms)=>setTimeout(fn,ms),cancel=handle=>clearTimeout(handle as ReturnType<typeof setTimeout>)}:{
 load:()=>Promise<T>;onStatus:(status:T)=>void;isVisible?:()=>boolean;
 schedule?:(fn:()=>void,ms:number)=>unknown;cancel?:(handle:unknown)=>void;
}){
 let stopped=false,busy=false,wakePending=false,timer:unknown;
 let running=false;
 const poll=async()=>{
  if(stopped)return;
  if(busy){wakePending=true;return;}
  if(timer!==undefined){cancel(timer);timer=undefined;}
  if(!isVisible()){timer=schedule(()=>void poll(),10000);return;}
  busy=true;
  try{const status=await load();if(!stopped){running=status.last_job?.status==='running';onStatus(status);}}
  catch{/* Keep the last saved view; retry without claiming fresh data. */}
  finally{busy=false;if(!stopped){const delay=wakePending?0:running?2000:10000;wakePending=false;timer=schedule(()=>void poll(),delay);}}
 };
 void poll();
 return {wake:()=>void poll(),stop:()=>{stopped=true;if(timer!==undefined)cancel(timer);}};
}
