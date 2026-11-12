import type { ScheduleDay } from './TrainingScheduleEditor';

export type PreferenceContext = { revision: number; answers: Record<string, unknown> & { week_schedule?: ScheduleDay[]; sports?: string[] } };

export function availabilityRequest(context: PreferenceContext, day: ScheduleDay, expectedRevision: number | undefined) {
  if (expectedRevision !== context.revision) throw new Error('Your training preferences changed while you were editing. Cancel and reopen this day to review the latest values.');
  const schedule = [...(context.answers.week_schedule ?? []).filter(d => d.weekday !== day.weekday), day].sort((a, b) => a.weekday - b.weekday);
  // Match the existing Training form: explicit weekly schedules supersede legacy fields.
  const { availability: _availability, weekly_minutes: _minutes, ...answers } = context.answers;
  return { answers: { ...answers, week_schedule: schedule }, expected_revision: expectedRevision };
}
