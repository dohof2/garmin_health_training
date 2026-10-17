/** Calendar dates, not 24-hour offsets: a DST change must not repeat or omit a day. */
export function trainingDate(instant:Date,timeZone:string):string {
  const values=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(instant).map(p=>[p.type,p.value]));
  return `${values.year}-${values.month}-${values.day}`;
}
export function trainingWeek(instant:Date,timeZone:string):string[] {
  const [year,month,day]=trainingDate(instant,timeZone).split('-').map(Number);
  return Array.from({length:7},(_,offset)=>new Date(Date.UTC(year,month-1,day+offset)).toISOString().slice(0,10));
}

export type WorkoutSchedule={scheduled_for:string;scheduled_date?:string;time_unspecified?:boolean;definition?:{scheduled_date?:string;time_unspecified?:boolean}};
export function workoutDate(workout:WorkoutSchedule,timeZone:string):string {
  return workout.scheduled_date??workout.definition?.scheduled_date??trainingDate(new Date(workout.scheduled_for),timeZone);
}
export function workoutLabel(workout:WorkoutSchedule,timeZone:string):string {
  if(workout.time_unspecified||workout.definition?.time_unspecified){
    const date=workoutDate(workout,timeZone);
    return new Date(`${date}T12:00:00Z`).toLocaleDateString([], {timeZone:'UTC',weekday:'long',month:'short',day:'numeric',year:'numeric'});
  }
  return new Date(workout.scheduled_for).toLocaleString([], {timeZone,weekday:'long',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}
