import {useEffect,useRef} from 'react';
import {WeightEntry} from './GraphCanvas';

export default function WeightEntryDialog({unit,onSaved,showButton}:{unit?:'kg'|'lb';onSaved:()=>void;showButton:boolean}){
  const dialog=useRef<HTMLDialogElement>(null);
  const open=()=>{if(!dialog.current?.open)dialog.current?.showModal();};
  useEffect(()=>{window.addEventListener('open-weight-entry',open);return()=>window.removeEventListener('open-weight-entry',open);},[]);
  return <>{showButton&&<button className="weight-entry-launch" type="button" onClick={open}>＋ Add weight</button>}<dialog ref={dialog} className="weight-entry-dialog" aria-label="Add weight measurement" onClick={e=>{if(e.target===e.currentTarget)dialog.current?.close();}}><button type="button" className="weight-dialog-close" aria-label="Close weight entry" onClick={()=>dialog.current?.close()}>×</button><WeightEntry unit={unit} onSaved={onSaved}/></dialog></>;
}
