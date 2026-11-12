import {useEffect,useState} from 'react';
import {api} from './GraphCanvas';
import ActivityRouteMap from './ActivityRouteMap';
import {ArrowRight,SportIcon} from './JournalIcons';
import {ridingTime} from './recentActivitySummary';
export type DashboardActivityRecord={id:string;name:string|null;activity_type:string;local_date:string;duration_seconds:number|null;distance_meters:number|null;calories_kcal:number|null};
type Detail={elevation_gain_meters:number|null;sample_summary:{average_heart_rate_bpm:number|null;average_power_watts:number|null}};
export default function DashboardActivity({activity,timezone,active,refresh,distanceUnit,onDetails}:{activity:DashboardActivityRecord|null;timezone:string;active:boolean;refresh:string;distanceUnit:'km'|'mi';onDetails:(id:string)=>void}) {
  const [detail,setDetail]=useState<{id:string;value:Detail}|null>(null);
  useEffect(()=>{
    if(!activity||!active)return;
    const controller=new AbortController();
    void api<Detail>(`/api/activities/${encodeURIComponent(activity.id)}?timezone=${encodeURIComponent(timezone)}`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setDetail({id:activity.id,value});}).catch(()=>{if(!controller.signal.aborted)setDetail(null);});
    return()=>controller.abort();
  },[activity?.id,active,refresh,timezone]);
  if(!activity)return <section className="journal-latest"><p className="journal-kicker">Latest activity</p><p>No recorded activity yet.</p></section>;
  const current=detail?.id===activity.id?detail.value:null;
  const distance=activity.distance_meters===null?'—':`${(activity.distance_meters/(distanceUnit==='mi'?1609.344:1000)).toLocaleString(undefined,{maximumFractionDigits:1})} ${distanceUnit}`;
  const metric=(value:number|null|undefined,unit:string)=>value==null?'—':`${Math.round(value).toLocaleString()} ${unit}`;
  return <section className="journal-latest" aria-labelledby="journal-latest-title">
    <div className="journal-week-heading"><div><p className="journal-kicker">Latest activity · {activity.local_date}</p><h2 id="journal-latest-title"><SportIcon sport={activity.activity_type}/>{activity.name??activity.activity_type.replaceAll('_',' ')}</h2></div><button type="button" className="journal-text-action" onClick={()=>onDetails(activity.id)}>More details <ArrowRight size={16}/></button></div>
    <dl className="journal-activity-stats"><div><dt>Time</dt><dd>{ridingTime(activity.duration_seconds)}</dd></div><div><dt>Distance</dt><dd>{distance}</dd></div><div><dt>Elevation gain</dt><dd>{metric(current?.elevation_gain_meters,'m')}</dd></div><div><dt>Avg. heart rate</dt><dd>{metric(current?.sample_summary.average_heart_rate_bpm,'bpm')}</dd></div><div><dt>Avg. power</dt><dd>{metric(current?.sample_summary.average_power_watts,'W')}</dd></div><div><dt>Energy</dt><dd>{metric(activity.calories_kcal,'kcal')}</dd></div></dl>
    {active&&<ActivityRouteMap key={`${activity.id}:${refresh}`} activityId={activity.id} distanceUnit={distanceUnit}/>}
  </section>;
}
