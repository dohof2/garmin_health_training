export type RouteMetric='power_watts'|'speed_mps'|'heart_rate_bpm'|'elevation_meters';
export type RoutePoint={latitude:number;longitude:number;recorded_at:string;segment:number}&Record<RouteMetric,number|null>;
export type RouteData={points:RoutePoint[];available_metrics:RouteMetric[];default_metric:RouteMetric|null;gps_sample_count:number;sampled:boolean};
export const metricLabels:Record<RouteMetric,string>={power_watts:'Power',speed_mps:'Speed',heart_rate_bpm:'Heart rate',elevation_meters:'Elevation'};
export function chooseMetric(data:RouteData,preferred:string|null):RouteMetric|null {
 return data.available_metrics.includes(preferred as RouteMetric)?preferred as RouteMetric:data.default_metric;
}
export function metricValue(metric:RouteMetric,value:number,unit:'km'|'mi') {
 return metric==='speed_mps'?`${(value*(unit==='mi'?2.236936:3.6)).toFixed(1)} ${unit==='mi'?'mph':'km/h'}`: `${Math.round(value)} ${metric==='power_watts'?'W':metric==='heart_rate_bpm'?'bpm':'m'}`;
}
export function routeColour(value:number|null,low:number,high:number) {
 if(value===null||!Number.isFinite(value))return '#89929c';
 const fraction=high===low?.5:Math.max(0,Math.min(1,(value-low)/(high-low)));
 return `hsl(${Math.round(220-220*fraction)}, 85%, 46%)`;
}

export type PowerStop={value:number;fraction:number};
// Smooth interpolation through quantiles keeps brief peaks from flattening
// the rest of the ride, without discrete colour boundaries.
export function powerScale(values:number[]):PowerStop[] {
 const working=values.filter(v=>Number.isFinite(v)&&v>0).sort((a,b)=>a-b);
 const stops:PowerStop[]=[{value:0,fraction:0}];
 if(!working.length)return stops;
 if(working[0]===working.at(-1))return [...stops,{value:working[0],fraction:.5}];
 for(const q of [.2,.4,.6,.8,.95,1]){
  const value=working[Math.floor((working.length-1)*q)];
  if(value>stops.at(-1)!.value)stops.push({value,fraction:q});
 }
 return stops;
}
export function powerColour(value:number|null,stops:PowerStop[]) {
 if(value===null||!Number.isFinite(value))return '#89929c';
 const upper=stops.findIndex(s=>value<=s.value);
 const a=upper>0?stops[upper-1]:stops[0],b=upper>=0?stops[upper]:stops.at(-1)!;
 const fraction=a.value===b.value?b.fraction:a.fraction+(b.fraction-a.fraction)*Math.max(0,Math.min(1,(value-a.value)/(b.value-a.value)));
 return `hsl(${(220-220*fraction).toFixed(3)}, 85%, 46%)`;
}
export function powerGradient(stops:PowerStop[]) {
 const maximum=stops.at(-1)?.fraction||1;
 return `linear-gradient(90deg, ${stops.map(s=>`${powerColour(s.value,stops)} ${s.fraction/maximum*100}%`).join(', ')})`;
}
