import {useEffect,useRef,useState} from 'react';
type Point={x:number;y:number;distance:number|null;segment:number};
type Trace={label:string;unit:string;points:Point[];sample_count:number};
type Recording={name:string|null;traces:Record<string,Trace>;distance_available:boolean;note:string};
const colours:Record<string,string>={speed:'#27836b',elevation:'#936d25',power:'#356799',cadence:'#8258b6',heart_rate:'#c44550'};
const clock=(seconds:number)=>`${Math.floor(seconds/60)}:${String(Math.round(seconds%60)).padStart(2,'0')}`;
export default function ActivityPlots({activityId}:{activityId:string}){
 const [open,setOpen]=useState(false),[data,setData]=useState<Recording|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{
  if(!open||data)return;
  const controller=new AbortController();setError('');
  void fetch(`/api/activities/${encodeURIComponent(activityId)}/plots`,{signal:controller.signal,cache:'no-store'})
   .then(async response=>{
    if(response.status===404)throw new Error('The running app has not loaded activity plots yet. Press Return in its launcher Terminal to quit, then reopen Open Garmin.command and retry. Refreshing the browser alone does not restart the app.');
    if(!response.ok)throw new Error('Activity plots could not be loaded. Please retry.');
    return response.json() as Promise<Recording>;
   }).then(result=>{if(!controller.signal.aborted)setData(result);})
   .catch(error=>{if(!controller.signal.aborted)setError(error instanceof Error?error.message:'Activity plots could not be loaded.');});
  return()=>controller.abort();
 },[activityId,open,data,retry]);
 return <><button type="button" aria-expanded={open} onClick={()=>setOpen(!open)}>{open?'Close plots':'Plots'}</button>{open&&<section aria-label="Recorded activity plots"><h3>{data?.name??'Activity'} · Plots</h3>{error&&<p role="alert">{error} <button type="button" onClick={()=>setRetry(value=>value+1)}>Retry plots</button></p>}{!data&&!error&&<p role="status">Loading recorded plots…</p>}{data&&<><p>{data.note}</p>{Object.entries(data.traces).filter(([,t])=>t.sample_count>0).map(([metric])=><TracePlot key={metric} metric={metric} data={data}/>)}{Object.values(data.traces).every(t=>!t.sample_count)&&<p>No recorded sensor samples are available.</p>}</>}</section>}</>;
}
function TracePlot({metric,data}:{metric:string;data:Recording}){
 const [selected,setSelected]=useState<string[]>([metric]),[axis,setAxis]=useState<'time'|'distance'>('time');
 // Zoom boundaries stay in elapsed seconds so axis switching preserves the same section.
 const [window,setWindow]=useState<[number,number]|null>(null),[drag,setDrag]=useState<[number,number]|null>(null),[hover,setHover]=useState<number|null>(null);
 const svg=useRef<SVGSVGElement>(null);
 const axisSpacing=80,width=680+Math.max(0,selected.length-1)*axisSpacing,height=365,left=88,right=650,top=26,bottom=285;
 const trace=data.traces[metric];
 const available=trace.points.filter(p=>axis==='time'||p.distance!==null);
 const visible=available.filter(p=>!window||p.x>=window[0]&&p.x<=window[1]);
 const xValue=(p:Point)=>axis==='time'?p.x:p.distance!;
 const xmin=visible.length?Math.min(...visible.map(xValue)):0,xmax=visible.length?Math.max(...visible.map(xValue)):1;
 const position=(p:Point)=>left+(xValue(p)-xmin)/(xmax-xmin||1)*(right-left);
 const fromPixel=(clientX:number)=>{const box=svg.current!.getBoundingClientRect();return Math.max(left,Math.min(right,(clientX-box.left)*width/box.width));};
 const nearest=(pixel:number)=>visible.reduce<Point|null>((best,p)=>!best||Math.abs(position(p)-pixel)<Math.abs(position(best)-pixel)?p:best,null);
 const finish=()=>{if(drag&&Math.abs(drag[1]-drag[0])>8){const a=nearest(Math.min(...drag)),b=nearest(Math.max(...drag));if(a&&b&&b.x>a.x)setWindow([a.x,b.x]);}setDrag(null);};
 const observed=hover===null?null:nearest(hover);
 return <article className="activity-trace"><h4>{trace.label}</h4><label>Horizontal axis <select value={axis} onChange={e=>setAxis(e.target.value as 'time'|'distance')}><option value="time">Elapsed time</option><option disabled={!data.distance_available} value="distance">Recorded distance</option></select></label> <button type="button" disabled={!window} onClick={()=>setWindow(null)}>Reset zoom</button>
 {!visible.length?<p>No recorded values for this axis/section.</p>:<div className="activity-trace-scroll" role="region" aria-label={`${trace.label} plot with labelled axes; scroll horizontally to view all overlay scales`} tabIndex={0}><svg ref={svg} viewBox={`0 0 ${width} ${height}`} style={{width:'100%',minWidth:width,display:'block',touchAction:'none',userSelect:'none'}} role="img" aria-label={`${trace.label} versus ${axis}. Drag to zoom; use Reset zoom to restore.`} onPointerDown={e=>{if(e.button!==0)return;e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);const px=fromPixel(e.clientX);setDrag([px,px]);}} onPointerMove={e=>{const px=fromPixel(e.clientX);setHover(px);setDrag(current=>current?[current[0],px]:null);}} onPointerUp={finish} onPointerCancel={()=>setDrag(null)} onPointerLeave={()=>setHover(null)}>
 <line x1={left} x2={right} y1={bottom} y2={bottom} stroke="currentColor"/>
 {[0,.25,.5,.75,1].map(f=><g key={f}><line x1={left+f*(right-left)} x2={left+f*(right-left)} y1={bottom} y2={bottom+5} stroke="currentColor"/><text x={left+f*(right-left)} y={bottom+23} textAnchor="middle" fontSize="13">{axis==='time'?clock(xmin+f*(xmax-xmin)):(xmin+f*(xmax-xmin)).toFixed(2)}</text></g>)}
 <text x={(left+right)/2} y={bottom+54} textAnchor="middle" fontSize="14" fontWeight="600">{axis==='time'?'Elapsed time (minutes:seconds)':'Recorded distance (km)'}</text>
 {selected.map((key,index)=>{
  const t=data.traces[key],points=t.points.filter(p=>(axis==='time'||p.distance!==null)&&xValue(p)>=xmin&&xValue(p)<=xmax&&(!window||p.x>=window[0]&&p.x<=window[1]));
  const axisX=index===0?left:right+(index-1)*axisSpacing,direction=index===0?-1:1,titleX=axisX+direction*62,midY=(top+bottom)/2;
  const rawLow=points.length?Math.min(...points.map(p=>p.y)):0,rawHigh=points.length?Math.max(...points.map(p=>p.y)):1;
  const pad=rawLow===rawHigh?Math.max(1,Math.abs(rawLow)*.05):0,lo=rawLow-pad,hi=rawHigh+pad;
  const y=(value:number)=>bottom-8-(value-lo)/(hi-lo)*(bottom-top-16);
  const format=(value:number)=>value.toLocaleString(undefined,{maximumFractionDigits:hi-lo<1?2:hi-lo<10?1:0});
  const segments:Point[][]=[];
  points.forEach((p,i)=>{if(i===0||p.segment!==points[i-1].segment||(axis==='distance'&&p.distance!<points[i-1].distance!))segments.push([]);segments.at(-1)!.push(p);});
  return <g key={key} aria-label={`${t.label} Y axis (${t.unit})`}>
   {index===0&&[0,.25,.5,.75,1].map(f=><line key={f} x1={left} x2={right} y1={y(lo+f*(hi-lo))} y2={y(lo+f*(hi-lo))} stroke="#dce4ef"/>)}
   <line x1={axisX} x2={axisX} y1={top+8} y2={bottom-8} stroke={colours[key]}/>
   {[0,.25,.5,.75,1].map(f=>{const value=lo+f*(hi-lo);return <g key={f}><line x1={axisX} x2={axisX+direction*5} y1={y(value)} y2={y(value)} stroke={colours[key]}/><text x={axisX+direction*9} y={y(value)+4} textAnchor={index===0?'end':'start'} fill={colours[key]} fontSize="12">{points.length?format(value):'—'}</text></g>;})}
   <text x={titleX} y={midY} transform={`rotate(${index===0?-90:90} ${titleX} ${midY})`} textAnchor="middle" fill={colours[key]} fontSize="13" fontWeight="600">{t.label} ({t.unit})</text>
   {segments.map((segment,i)=><polyline key={i} points={segment.map(p=>`${position(p)},${y(p.y)}`).join(' ')} fill="none" stroke={colours[key]} strokeWidth="1.7"/>)}
  </g>;
 })}
 {observed&&<line x1={position(observed)} x2={position(observed)} y1={top} y2={bottom} stroke="currentColor" strokeDasharray="4 4"/>}
 {drag&&<rect x={Math.min(...drag)} y={top} width={Math.abs(drag[1]-drag[0])} height={bottom-top} fill="#356799" opacity=".15"/>}
 </svg></div>}
 {observed&&<p role="status">{clock(observed.x)}{observed.distance!==null?` · ${observed.distance.toFixed(2)} km`:''} · {selected.map(key=>{const point=data.traces[key].points.find(p=>p.x===observed.x);return `${data.traces[key].label}: ${point?`${point.y.toFixed(1)} ${data.traces[key].unit}`:'no displayed sample at this timestamp'}`;}).join(' · ')}</p>}
 <fieldset><legend>Overlay recorded metrics · each has its own coloured Y axis</legend>{Object.entries(data.traces).map(([key,t])=><label key={key} style={{color:colours[key],marginRight:12}}><input type="checkbox" checked={selected.includes(key)} disabled={key===metric||!t.sample_count} onChange={e=>setSelected(current=>e.target.checked?[...current,key]:current.filter(k=>k!==key))}/>{t.label} ({t.unit})</label>)}</fieldset>
 </article>;
}
