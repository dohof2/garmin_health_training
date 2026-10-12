import {useState} from 'react';
export type Adjustment={workout_id:string;expected_revision:number;changes:Record<string,unknown>;message:string;kind:string};
export default function TrainingAdjustmentProposal({proposal}:{proposal:Adjustment}) {
  const [status,setStatus]=useState(''),[busy,setBusy]=useState(false),[saved,setSaved]=useState(false);
  return <div className="training-notice"><strong>Review training change</strong><p>{proposal.message}</p>{typeof proposal.changes.notes==='string'&&<p>{proposal.changes.notes}</p>}<button type="button" disabled={busy||saved} onClick={async()=>{setBusy(true);setStatus('');try{
    const url=`/api/training/workouts/${encodeURIComponent(proposal.workout_id)}${proposal.kind==='schedule'?'/schedule':''}`;
    const response=await fetch(url,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:proposal.expected_revision,changes:proposal.changes})});
    const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not save training change');setSaved(true);setStatus('Saved to your active plan.');window.dispatchEvent(new Event('training-plan-changed'));
  }catch(e){setStatus(e instanceof Error?e.message:'Could not save training change');}finally{setBusy(false);}}}>{saved?'Saved':busy?'Saving…':'Save training change'}</button>{status&&<p role="status">{status}</p>}</div>;
}
