import {useState, type ReactNode} from 'react';

type Stats = {records: Record<string,unknown>[]; statistics: Record<string,{unit?:string|null}>; total_records:number; original_available:boolean};
type Detail = {started_at:string; ended_at:string|null; duration_seconds:number|null; distance_meters:number|null; calories_kcal:number|null; elevation_gain_meters:number|null;activity_metrics: {metric_type:string;value:number;unit:string}[];sample_summary:Record<string,number|string|null>};
type Item = {label:string;value:number|null;unit?:string;duration?:boolean};
function trainerGroups(detail:Detail, fit:Stats): {title:string;items:Item[]}[] {
  const session=fit.records[0]??{};
  const metrics=new Map(detail.activity_metrics.map(m=>[m.metric_type,m.value]));
  const numeric=(value:unknown):number|null=>typeof value==='number'&&Number.isFinite(value)?value:null;
  const recorded=(metric:string,fields:string[],sample?:string):number|null=>{
    const metricValue=metrics.get(metric);if(metricValue!==undefined)return metricValue;
    for(const field of fields){const value=numeric(session[field]);if(value!==null)return value;}
    return sample?numeric(detail.sample_summary[sample]):null;
  };
  const item=(label:string,metric:string,fields:string[],unit:string,sample?:string):Item=>({label,value:recorded(metric,fields,sample),unit});
  const distance=detail.distance_meters??numeric(session.total_distance);
  const speed=recorded('average_speed',['enhanced_avg_speed','avg_speed'],'average_speed_mps');
  const groups=[
    {title:'Ride volume',items:[
      {label:'Riding time',value:numeric(session.total_timer_time)??detail.duration_seconds,duration:true},
      {label:'Distance',value:distance===null?null:distance/1000,unit:'km'},
      {label:'Total climb',value:detail.elevation_gain_meters??numeric(session.total_ascent),unit:'m'},
      {label:'Average speed',value:speed===null?null:speed*3.6,unit:'km/h'},
      {label:'Calories',value:detail.calories_kcal,unit:'kcal'},
    ]},
    {title:'Effort & technique',items:[
      item('Average heart rate','average_heart_rate',['avg_heart_rate'],'bpm','average_heart_rate_bpm'),
      item('Maximum heart rate','maximum_heart_rate',['max_heart_rate'],'bpm','maximum_heart_rate_bpm'),
      item('Average power','average_power',['avg_power'],'W','average_power_watts'),
      item('Normalized power','normalized_power',['normalized_power'],'W'),
      item('Maximum power','maximum_power',['max_power'],'W','maximum_power_watts'),
      item('Average cadence','average_cadence',['avg_cadence'],'rpm','average_cadence_rpm'),
    ]},
    {title:'Training stimulus',items:[
      item('Training load','exercise_load',['training_load_peak'],'Garmin load'),
      item('Training stress score','training_stress_score',['training_stress_score'],'TSS'),
      item('Intensity factor','intensity_factor',['intensity_factor'],''),
      item('Aerobic training effect','aerobic_training_effect',['total_training_effect'],'/ 5'),
      item('Anaerobic training effect','anaerobic_training_effect',['total_anaerobic_training_effect'],'/ 5'),
    ]},
  ];
  return groups.map(group=>({...group,items:group.items.filter(i=>i.value!==null)})).filter(group=>group.items.length>0);
}
function display(item:Item):string {
  if(item.value===null)return 'Not recorded';
  if(item.duration){const minutes=Math.round(item.value/60);return minutes>=60?`${Math.floor(minutes/60)}h ${minutes%60}m`:`${minutes} min`;}
  const precision=item.unit==='km'||item.unit==='km/h'||item.unit==='/ 5'?1:item.label==='Intensity factor'?2:0;
  return `${item.value.toLocaleString(undefined,{maximumFractionDigits:precision})} ${item.unit??''}`.trim();
}
export default function FullActivityStats({activity,timezone,footer}:{activity:{id:string;name:string|null};timezone:string;footer?:ReactNode}) {
  const [open,setOpen]=useState(false),[data,setData]=useState<{detail:Detail;fit:Stats}|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  async function show(){setOpen(true);if(data||loading)return;setLoading(true);setError('');try{
    const base=`/api/activities/${encodeURIComponent(activity.id)}`;
    const responses=await Promise.all([fetch(`${base}?timezone=${encodeURIComponent(timezone)}`),fetch(`${base}/full-stats?timezone=${encodeURIComponent(timezone)}`)]);
    if(responses.some(r=>!r.ok))throw new Error('Could not load the full recorded statistics. Please retry.');
    const [detail,fit]=await Promise.all(responses.map(r=>r.json()));setData({detail,fit});
  }catch(e){setError(e instanceof Error?e.message:'Could not load statistics');}finally{setLoading(false);}}
  return <div className="full-activity-stats">
    <button type="button" aria-expanded={open} onClick={()=>open?setOpen(false):void show()}>{open?'Close details':'More details'}</button>
    {open&&<section aria-label={`Training statistics for ${activity.name??'activity'}`}>
      <h3>{activity.name??'Activity'} · Training summary</h3>
      {loading&&<p role="status">Loading ride statistics…</p>}
      {error&&<p role="alert">{error} <button type="button" onClick={()=>void show()}>Retry</button></p>}
      {data&&<>
        {trainerGroups(data.detail,data.fit).map(group=><div key={group.title}>
          <h4>{group.title}</h4><div className="activity-detail-grid">{group.items.map(item=><div key={item.label}><span>{item.label}</span><strong>{display(item)}</strong></div>)}</div>
        </div>)}
        <p className="graph-meta">Recorded ride statistics. Unavailable measurements are omitted.</p>
      </>}
      {footer}
    </section>}
  </div>;
}
