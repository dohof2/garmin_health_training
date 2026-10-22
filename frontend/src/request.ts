type Pending={promise:Promise<Response>;controller:AbortController;subscribers:number;finished:boolean};
const pending=new Map<string,Pending>();

// Share simultaneous reads, never write actions. Abort belongs to each caller;
// abort the shared transfer only when no caller still needs it. No stale TTL cache.
export function coalescedFetch(url:string,options:RequestInit={}):Promise<Response>{
 const method=(options.method??'GET').toUpperCase();
 if(method!=='GET'&&!(method==='POST'&&url==='/api/charts/query'))return fetch(url,options).then(response=>{if(response.ok)pending.clear();return response;});
 const signal=options.signal;
 if(signal?.aborted)return Promise.reject(new DOMException('Request aborted','AbortError'));
 const key=JSON.stringify([url,method,options.body??null,[...new Headers(options.headers).entries()],options.credentials??'same-origin']);
 let entry=pending.get(key);
 if(!entry){
  const controller=new AbortController();
  entry={controller,subscribers:0,finished:false,promise:Promise.resolve(null as unknown as Response)};
  const created=entry;
  entry.promise=fetch(url,{...options,signal:controller.signal}).finally(()=>{created.finished=true;if(pending.get(key)===created)pending.delete(key);});
  pending.set(key,entry);
 }
 const shared=entry;shared.subscribers++;
 return new Promise((resolve,reject)=>{
  let released=false;
  const release=()=>{if(released)return;released=true;signal?.removeEventListener('abort',abort);shared.subscribers--;queueMicrotask(()=>{if(!shared.finished&&shared.subscribers===0){if(pending.get(key)===shared)pending.delete(key);shared.controller.abort();}});};
  const abort=()=>{release();reject(new DOMException('Request aborted','AbortError'));};
  signal?.addEventListener('abort',abort,{once:true});
  shared.promise.then(response=>{if(!released){release();resolve(response.clone());}},error=>{if(!released){release();reject(error);}});
 });
}

export async function requestJson<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await coalescedFetch(url,options);
 const result=await response.json();
 if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'The request could not be completed.');
 return result as T;
}
