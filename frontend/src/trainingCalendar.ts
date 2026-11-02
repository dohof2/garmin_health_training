/** Calendar dates, not 24-hour offsets: a DST change must not repeat or omit a day. */
export function trainingDate(instant:Date,timeZone:string):string {
  const values=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(instant).map(p=>[p.type,p.value]));
  return `${values.year}-${values.month}-${values.day}`;
}
export function trainingWeek(instant:Date,timeZone:string):string[] {
  const [year,month,day]=trainingDate(instant,timeZone).split('-').map(Number);
  return Array.from({length:7},(_,offset)=>new Date(Date.UTC(year,month-1,day+offset)).toISOString().slice(0,10));
}

/** Completed records take precedence if refresh responses contain both states. */
export function mergeWorkoutStatus<T extends {id:string;completion_status:string}>(planned:T[],completed:T[]):T[] {
  const entries=new Map<string,T>();
  for(const workout of [...planned,...completed]) {
    if(workout.completion_status==='cancelled')continue;
    const existing=entries.get(workout.id);
    if(!existing||existing.completion_status!=='completed')entries.set(workout.id,workout);
  }
  return [...entries.values()];
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
