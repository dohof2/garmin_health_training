import type {ScheduleDay,WeeklyCaps} from './TrainingScheduleEditor';
export type CandidatePreferences = {
  week_schedule?:ScheduleDay[];weekly_caps?:WeeklyCaps;
  availability: {weekday:number;start_time:string|null;minutes:number}[];
  sports: string[];
  weekly_minutes: Record<string,number>;
};

// Review responses contain patches, not necessarily a complete questionnaire.
// Defaults here are display-only; do not turn missing answers into saved facts.
export function candidatePreferences(saved: CandidatePreferences, patch?: Partial<CandidatePreferences>): CandidatePreferences {
  return {
    ...saved,
    ...patch,
    week_schedule:patch?.week_schedule?[...(saved.week_schedule??[]).filter(day=>!patch.week_schedule!.some(update=>update.weekday===day.weekday)),...patch.week_schedule].sort((a,b)=>a.weekday-b.weekday):saved.week_schedule??[],
    weekly_caps:{...saved.weekly_caps,...patch?.weekly_caps},
    sports: patch?.sports ?? saved.sports ?? [],
    availability: patch?.availability ?? saved.availability ?? [],
    weekly_minutes: {...saved.weekly_minutes, ...patch?.weekly_minutes},
  };
}

export function sameCandidate(left: unknown, right: unknown): boolean {
  const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).filter(([,v])=>v!==undefined).sort(([a],[b])=>a.localeCompare(b)).map(([key,v])=>[key,canonical(v)])):value;
  return JSON.stringify(canonical(left))===JSON.stringify(canonical(right));
}
