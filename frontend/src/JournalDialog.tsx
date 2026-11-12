import {useEffect,useId,useRef,type ReactNode} from 'react';
import {X} from './JournalIcons';

export default function JournalDialog({open,title,onClose,children}:{open:boolean;title:string;onClose:()=>void;children:ReactNode}) {
  const ref=useRef<HTMLDialogElement>(null),heading=useId();
  useEffect(()=>{if(open&&!ref.current?.open)ref.current?.showModal();else if(!open)ref.current?.close();},[open]);
  return <dialog ref={ref} className="journal-detail-dialog" aria-labelledby={heading} onClose={onClose}>
    <div className="journal-dialog-heading"><h2 id={heading}>{title}</h2><button type="button" aria-label="Close details" onClick={()=>ref.current?.close()}><X size={22}/></button></div>
    {open&&children}
  </dialog>;
}
