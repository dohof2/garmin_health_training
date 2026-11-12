// Reviewed anatomical groups for the app's curated planning catalog.
// Reference: NASM exercise library, https://www.nasm.org/workout-exercise-guidance
// Roles describe typical prime movers and support, not measured activation.
export type Muscle='chest'|'shoulders'|'biceps'|'triceps'|'forearms'|'abs'|'obliques'|'quads'|'calves'|'lats'|'upper_back'|'lower_back'|'glutes'|'hamstrings';
export const muscleNames:Record<Muscle,string>={chest:'Chest',shoulders:'Shoulders',biceps:'Biceps',triceps:'Triceps',forearms:'Forearms',abs:'Abdominals',obliques:'Obliques',quads:'Quadriceps',calves:'Calves',lats:'Lats',upper_back:'Upper back',lower_back:'Lower back',glutes:'Glutes',hamstrings:'Hamstrings'};
export type MuscleProfile={primary:Muscle[];secondary:Muscle[]};
const squat:MuscleProfile={primary:['quads','glutes'],secondary:['abs','lower_back','hamstrings','calves']};
const row:MuscleProfile={primary:['lats','upper_back'],secondary:['biceps','shoulders','forearms']};
const press:MuscleProfile={primary:['chest'],secondary:['triceps','shoulders']};
const deadlift:MuscleProfile={primary:['glutes','quads','hamstrings'],secondary:['lower_back','upper_back','abs','forearms']};
export const exerciseMuscles:Record<string,MuscleProfile>={
 air_squat:squat,dumbbell_squat:squat,barbell_squat:squat,band_squat:squat,machine_leg_press:{primary:['quads','glutes'],secondary:['hamstrings','calves']},
 dumbbell_row:row,band_row:row,seated_cable_row:row,barbell_row:{primary:row.primary,secondary:[...row.secondary,'lower_back','abs']},
 dumbbell_press:press,band_chest_press:press,kneeling_pushup:{primary:['chest'],secondary:['triceps','shoulders','abs']},pushup:{primary:['chest'],secondary:['triceps','shoulders','abs']},
 pullup_progression:{primary:['lats','upper_back'],secondary:['biceps','shoulders','forearms','abs']},
 dip_progression:{primary:['triceps','chest'],secondary:['shoulders','abs']},
 hip_raise:{primary:['glutes'],secondary:['hamstrings','abs']},dead_bug:{primary:['abs','obliques'],secondary:[]},
 dumbbell_deadlift:deadlift,barbell_deadlift:deadlift,calf_raise:{primary:['calves'],secondary:[]},
};
const aliases:Record<string,string>={pull_up:'pullup_progression',body_weight_dip:'dip_progression',dumbbell_floor_press:'dumbbell_press',chest_press_with_band:'band_chest_press',leg_press:'machine_leg_press',barbell_back_squat:'barbell_squat',kneeling_push_up:'kneeling_pushup',push_up:'pushup'};
export function muscleProfile(id?:string,name?:string) {
 const key=id&&exerciseMuscles[id]?id:(name??'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');
 return exerciseMuscles[key]??exerciseMuscles[aliases[key]];
}

export function combinedMuscles(exercises:{id?:string;name:string}[]):MuscleProfile|undefined {
 const profiles=exercises.map(e=>muscleProfile(e.id,e.name)).filter((p):p is MuscleProfile=>!!p);
 if(!profiles.length)return undefined;
 const primary=[...new Set(profiles.flatMap(p=>p.primary))];
 return {primary,secondary:[...new Set(profiles.flatMap(p=>p.secondary))].filter(m=>!primary.includes(m))};
}
