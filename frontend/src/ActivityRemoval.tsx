import {useEffect,useRef,useState} from 'react';
import {api} from './GraphCanvas';
type Item={id:string;name:string|null;activity_type:string;started_at:string};
const change=(id:string,removed:boolean)=>api(`/api/activities/${encodeURIComponent(id)}/removed`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({removed})});
export function RemoveActivity({activity,onChanged}:{activity:Item;onChanged:()=>void}){
  const [confirm,setConfirm]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const cancel=useRef<HTMLButtonElement>(null),trigger=useRef<HTMLButtonElement>(null);
  useEffect(()=>{if(confirm)cancel.current?.focus();},[confirm]);
  const close=()=>{setConfirm(false);trigger.current?.focus();};
  const name=activity.name??activity.activity_type.replaceAll('_',' ');
  return <div className="activity-removal"><button ref={trigger} type="button" onClick={()=>{setError('');setConfirm(true);}} aria-label={`Remove ${name}`}>Remove activity</button>{confirm&&<div className="activity-removal-confirm" role="alertdialog" aria-label={`Remove ${name}?`} onKeyDown={e=>{if(e.key==='Escape'&&!busy){e.preventDefault();close();}}}><strong>Are you sure you want to remove “{name}”?</strong><p>{new Date(activity.started_at).toLocaleString()} · This removes it from this app’s activity history, plots and calculations. It stays in your Garmin account. You can restore it below.</p><div className="graph-actions"><button ref={cancel} type="button" disabled={busy} onClick={close}>Cancel</button><button className="danger-button" type="button" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{await change(activity.id,true);onChanged();}catch(e){setError(e instanceof Error?e.message:'Could not remove activity');}finally{setBusy(false);}}}>{busy?'Removing…':'Yes, remove activity'}</button></div>{error&&<p role="alert">{error}</p>}</div>}</div>;
}
export function RemovedActivities({revision,onChanged}:{revision:number;onChanged:()=>void}){
  const [items,setItems]=useState<Item[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState<string|null>(null);
  useEffect(()=>{const controller=new AbortController();api<{activities:Item[]}>('/api/activities/removed',{signal:controller.signal}).then(r=>setItems(r.activities)).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>controller.abort();},[revision]);
  return <details className="removed-activities"><summary>Removed activities ({items.length})</summary><p>Activities removed from this app can be restored here.</p>{error&&<p role="alert">{error}</p>}{items.map(item=><div className="removed-activity" key={item.id}><span><strong>{item.name??item.activity_type.replaceAll('_',' ')}</strong> · {new Date(item.started_at).toLocaleDateString()}</span><button type="button" disabled={!!busy} onClick={async()=>{setBusy(item.id);setError('');try{await change(item.id,false);onChanged();}catch(e){setError(e instanceof Error?e.message:'Could not restore activity');}finally{setBusy(null);}}}>{busy===item.id?'Restoring…':'Restore activity'}</button></div>)}</details>;
}
