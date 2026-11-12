import {useEffect,useRef,useState} from 'react';
import type {Map as LeafletMap,LayerGroup} from 'leaflet';
import {chooseMetric,metricLabels,metricValue,routeColour,powerScale,powerColour,powerGradient,type RouteData,type RouteMetric} from './routeMetrics';

export default function ActivityRouteMap({activityId,distanceUnit}:{activityId:string;distanceUnit:'km'|'mi'}) {
 const [data,setData]=useState<RouteData|null>(null),[error,setError]=useState('');
 const [metric,setMetric]=useState<RouteMetric|null>(null),[ready,setReady]=useState(false),[tilesFailed,setTilesFailed]=useState(false);
 const element=useRef<HTMLDivElement>(null),map=useRef<LeafletMap|null>(null),layers=useRef<LayerGroup|null>(null);
 useEffect(()=>{
  const controller=new AbortController();setData(null);setError('');
  fetch(`/api/activities/${encodeURIComponent(activityId)}/route`,{signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error('Could not load the recorded route.');return r.json() as Promise<RouteData>;}).then(result=>{
   if(controller.signal.aborted)return;
   let preference=null;try{preference=localStorage.getItem('garmin-route-colour-v1');}catch{/* Use automatic metric. */}
   setMetric(chooseMetric(result,preference));setData(result);
  }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Could not load route.');});
  return()=>controller.abort();
 },[activityId]);
 // A new activity detail mount always creates a fresh map and fits the whole route.
 useEffect(()=>{
  if(!data?.points.length||!element.current)return;
  let cancelled=false;let observer:ResizeObserver|undefined;
  void import('leaflet').then(L=>{
   if(cancelled||!element.current)return;
   const view=L.map(element.current,{scrollWheelZoom:false,preferCanvas:true,maxZoom:19});map.current=view;
   L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',crossOrigin:true}).on('tileerror',()=>{if(!cancelled)setTilesFailed(true);}).addTo(view);
   const bounds=L.latLngBounds(data.points.map(p=>[p.latitude,p.longitude] as [number,number]));
   view.fitBounds(bounds,{padding:[24,24],maxZoom:16,animate:false});
   observer=new ResizeObserver(()=>view.invalidateSize({pan:false}));observer.observe(element.current);
   layers.current=L.layerGroup().addTo(view);setReady(true);
  }).catch(()=>{if(!cancelled)setError('The route map could not be loaded.');});
  return()=>{cancelled=true;observer?.disconnect();map.current?.remove();map.current=null;layers.current=null;setReady(false);};
 },[data,activityId]);
 useEffect(()=>{
  if(!ready||!data||!layers.current)return;
  let cancelled=false;
  void import('leaflet').then(L=>{
   if(cancelled||!layers.current)return;
   const group=layers.current;group.clearLayers();
   const values=metric?data.points.flatMap(p=>p[metric]===null?[]:[p[metric]!]):[];
   const low=values.length?Math.min(...values):0,high=values.length?Math.max(...values):0;
   const bands=powerScale(values);
   for(let i=1;i<data.points.length;i++){
    const a=data.points[i-1],b=data.points[i];if(a.segment!==b.segment)continue;
    const value=metric?b[metric]:null;
    L.polyline([[a.latitude,a.longitude],[b.latitude,b.longitude]],{color:metric==='power_watts'?powerColour(value,bands):routeColour(value,low,high),weight:5,opacity:.95}).bindTooltip(metric&&value!==null?`${metricLabels[metric]}: ${metricValue(metric,value,distanceUnit)}`:'No recorded value').addTo(group);
   }
   const first=data.points[0],last=data.points.at(-1)!;
   L.circleMarker([first.latitude,first.longitude],{radius:7,color:'#fff',weight:2,fillColor:'#16834a',fillOpacity:1}).bindTooltip('Start').addTo(group);
   L.circleMarker([last.latitude,last.longitude],{radius:6,color:'#fff',weight:2,fillColor:'#202b38',fillOpacity:1}).bindTooltip('Finish').addTo(group);
  });return()=>{cancelled=true;};
 },[data,metric,ready,distanceUnit]);
 if(error)return <p role="status">{error}</p>;
 if(!data)return <p>Loading recorded route…</p>;
 if(!data.points.length)return <p className="graph-meta">No GPS route was recorded for this activity.</p>;
 const values=metric?data.points.flatMap(p=>p[metric]===null?[]:[p[metric]!]):[];
 return <section className="activity-route" aria-label="Activity route">
  <div className="route-heading"><h3>Recorded route</h3><label>Colour by <select value={metric??''} disabled={!data.available_metrics.length} onChange={e=>{const next=e.target.value as RouteMetric;setMetric(next);try{localStorage.setItem('garmin-route-colour-v1',next);}catch{/* Selection still works. */}}}>{!metric&&<option value="">Route only</option>}{data.available_metrics.map(key=><option key={key} value={key}>{metricLabels[key]}</option>)}</select></label><button type="button" disabled={!ready} onClick={()=>{void import('leaflet').then(L=>map.current?.fitBounds(L.latLngBounds(data.points.map(p=>[p.latitude,p.longitude] as [number,number])),{padding:[24,24],maxZoom:16,animate:false}));}}>Fit route</button></div>
  <div ref={element} className="activity-route-map" role="region" aria-label="Recorded GPS course map"/>
  {metric==='power_watts'&&values.length>0&&<><div className="route-legend"><span>0 W</span><span className="route-gradient" style={{background:powerGradient(powerScale(values))}}/><span>{Math.round(Math.max(...values))} W</span><small>Grey: no recorded value</small></div><p className="graph-meta">Continuous power colours follow this ride’s distribution, so brief peaks do not flatten the range. Hover over the route for watts.</p></>}
  {metric&&metric!=='power_watts'&&values.length>0&&<div className="route-legend"><span>{metricValue(metric,Math.min(...values),distanceUnit)}</span><span className="route-gradient"/><span>{metricValue(metric,Math.max(...values),distanceUnit)}</span><small>Grey: no recorded value</small></div>}
  {tilesFailed&&<p role="status">Background map tiles are unavailable. Your recorded route is still shown.</p>}
  {data.sampled&&<p className="graph-meta">Route simplified for display; original GPS and sensor samples are retained.</p>}
 </section>;
}
