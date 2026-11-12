export type RecordedActivity = { id:string; local_date:string; activity_type:string; duration_seconds:number|null; distance_meters:number|null };
export function sevenDayRange(today:string) {
  const start=new Date(`${today}T12:00:00Z`);
  start.setUTCDate(start.getUTCDate()-6);
  return {start:start.toISOString().slice(0,10),end:today};
}
export async function allRecentActivities(readPage:(offset:number)=>Promise<RecordedActivity[]>) {
  const records=new Map<string,RecordedActivity>();
  for(let offset=0;;offset+=100){
    const page=await readPage(offset);
    const before=records.size;
    for(const record of page)records.set(record.id,record);
    if(page.length<100)return [...records.values()];
    if(records.size===before)throw new Error('Activity history could not be fully read. Please retry.');
  }
}
export function summarizeActivities(records:RecordedActivity[],range:{start:string;end:string}) {
  const unique=[...new Map(records.map(record=>[record.id,record])).values()].filter(record=>record.local_date>=range.start&&record.local_date<=range.end);
  const rides=unique.filter(record=>/cycl|bik|virtual_ride|indoor_ride|bmx/i.test(record.activity_type));
  const valid=(value:number|null):value is number=>typeof value==='number'&&Number.isFinite(value)&&value>=0;
  const times=rides.filter(record=>valid(record.duration_seconds)),distances=rides.filter(record=>valid(record.distance_meters));
  return {
    strength:unique.filter(record=>/strength|weight_training|resistance_training/i.test(record.activity_type)).length,
    rides:rides.length,
    ridingSeconds:rides.length&&!times.length?null:times.reduce((sum,record)=>sum+record.duration_seconds!,0),
    ridingKm:rides.length&&!distances.length?null:distances.reduce((sum,record)=>sum+record.distance_meters!,0)/1000,
    missingTime:rides.length-times.length,
    missingDistance:rides.length-distances.length,
  };
}
export function ridingTime(seconds:number|null) {
  if(seconds===null)return '—';
  const minutes=Math.round(seconds/60),hours=Math.floor(minutes/60);
  return hours?`${hours}h ${minutes%60}m`:`${minutes} min`;
}

export function dailyRidingSummary(records:RecordedActivity[],range:{start:string;end:string}) {
  const days=[];
  for(const date=new Date(`${range.start}T12:00:00Z`);date.toISOString().slice(0,10)<=range.end;date.setUTCDate(date.getUTCDate()+1)) {
    const day=date.toISOString().slice(0,10);
    days.push({date:day,...summarizeActivities(records,{start:day,end:day})});
  }
  return days;
}
