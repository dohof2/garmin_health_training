import {Children,cloneElement,isValidElement,useState,useEffect,useRef,type ReactElement,type ReactNode,type HTMLAttributes} from 'react';

type CardProps=HTMLAttributes<HTMLElement>&{children?:ReactNode;active?:boolean;'data-sort-id'?:string};
// Reorder React children rather than moving DOM nodes, keeping forms and charts mounted.
export default function SortableCards({id,children,className,as:Tag='div',pageSections=false}:{id:string;children:ReactNode;className?:string;as?:'div'|'main';pageSections?:boolean}){
  const storageKey=`garmin-card-order:${id}`;
  const [saved,setSaved]=useState<string[]>(()=>{try{const value=JSON.parse(localStorage.getItem(storageKey)??'[]');return Array.isArray(value)?value.filter((item:unknown)=>typeof item==='string'):[];}catch{return [];}});
  useEffect(()=>{try{const value=JSON.parse(localStorage.getItem(storageKey)??'[]');setSaved(Array.isArray(value)?value.filter((item:unknown)=>typeof item==='string'):[]);}catch{setSaved([]);}},[storageKey]);
  const moving=useRef<{from:string;to:string}|null>(null);
  const [dragged,setDragged]=useState<string|null>(null),[over,setOver]=useState<string|null>(null);
  const entries=Children.toArray(children).map((node,index)=>({node,id:isValidElement(node)?String(node.key??index):String(index)}));
  const eligible=entries.filter(({node})=>isValidElement<CardProps>(node)&&!node.props.hidden&&(!pageSections||((typeof node.type==='string'&&(['section','article','form','details'].includes(node.type)||/^(maintenance-totals|maintenance-table|maintenance-csv)$/.test(node.props.className??''))&&!node.props.hidden)||node.props.active===true)));
  const keys=new Set(eligible.map(e=>e.id));
  const order=[...saved.filter(key=>keys.has(key)),...eligible.map(e=>e.id).filter(key=>!saved.includes(key))];
  const reorder=(from:string,to:string)=>{if(from===to)return;const next=[...order];next.splice(next.indexOf(from),1);next.splice(next.indexOf(to),0,from);setSaved(next);try{localStorage.setItem(storageKey,JSON.stringify(next));}catch{/* Ordering remains usable when browser storage is unavailable. */}};
  let cursor=0;
  const byId=new Map(eligible.map(entry=>[entry.id,entry]));
  const arranged=entries.map(entry=>keys.has(entry.id)?byId.get(order[cursor++])??entry:entry);
  return <Tag className={className} data-sort-group={id}>{arranged.map(({node,id:key})=>{
    if(!keys.has(key)||!isValidElement<CardProps>(node)){if(isValidElement<CardProps>(node)&&typeof node.props.active==='boolean')return <div key={key} hidden={!node.props.active} className="sortable-section">{node}</div>;return node;}
    const element=node as ReactElement<CardProps>;
    const title=typeof element.props['aria-label']==='string'?element.props['aria-label']:'card';
    const handle=eligible.length<2?null:<button key="drag-handle" type="button" className="card-drag-handle" aria-label={`Move ${title}`} title="Drag to rearrange. Use arrow keys to move." onPointerDown={e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();e.currentTarget.setPointerCapture(e.pointerId);moving.current={from:key,to:key};setDragged(key);}} onPointerMove={e=>{if(!moving.current)return;const target=document.elementFromPoint(e.clientX,e.clientY)?.closest<HTMLElement>('[data-sort-id]');if(target?.closest('[data-sort-group]')===e.currentTarget.closest('[data-sort-group]')&&target?.dataset.sortId&&keys.has(target.dataset.sortId)){moving.current.to=target.dataset.sortId;setOver(target.dataset.sortId);}if(e.clientY>window.innerHeight-50)window.scrollBy(0,20);else if(e.clientY<50)window.scrollBy(0,-20);}} onPointerUp={e=>{e.stopPropagation();const move=moving.current;if(move)reorder(move.from,move.to);moving.current=null;setDragged(null);setOver(null);}} onPointerCancel={()=>{moving.current=null;setDragged(null);setOver(null);}} onKeyDown={e=>{if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const index=order.indexOf(key),target=index+(['ArrowUp','ArrowLeft'].includes(e.key)?-1:1);if(order[target])reorder(key,order[target]);}}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/></svg></button>;
    const props:CardProps={'data-sort-id':key,className:`${element.props.className??''} sortable-card ${over===key?'sortable-card--target':''}`,onDragOver:e=>{if(!dragged)return;e.preventDefault();e.stopPropagation();setOver(key);},onDrop:e=>{if(!dragged)return;e.preventDefault();e.stopPropagation();reorder(dragged,key);setDragged(null);setOver(null);}};
    return typeof element.type==='string'?cloneElement(element,{...props,key},handle,element.props.children):<div key={key} {...props} hidden={element.props.active===false}>{handle}{element}</div>;
  })}</Tag>;
}
