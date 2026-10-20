type Step={name?:string;type:string;effort:string;target?:{type:string;lower:number;upper:number;unit:string};power_reference_fractions?:{lower:number;upper:number}};
export type FtpReference={watts:number;measurement_date?:string|null;source?:string;status:string;advisory_only:boolean};
type PowerWorkout={sport?:string;template_id?:string;reference_ftp?:FtpReference;reference_ftp_watts?:number;steps?:Step[];effort_target?:{description:string}};

// Only explicit planner-provided fractions can produce advisory watt ranges.
// The saved effort prescription and FTP measurement date remain unchanged.
export function displayPower<T extends PowerWorkout>(definition:T):T {
  const ftp=definition.reference_ftp?.watts;
  const cycling=definition.sport==='cycling'||definition.template_id?.startsWith('cycling_');
  if(!cycling||!ftp||!Number.isFinite(ftp)||ftp<=0||definition.reference_ftp?.status==='future'||!definition.steps)return definition;
  let changed=false;
  const steps=definition.steps.map(step=>{
    if(step.target?.type!=='perceived_effort')return step;
    const fractions=step.power_reference_fractions;
    if(!fractions||!Number.isFinite(fractions.lower)||!Number.isFinite(fractions.upper)||fractions.lower<0||fractions.upper<fractions.lower)return step;
    const lower=Math.round(ftp*fractions.lower),upper=Math.round(ftp*fractions.upper);changed=true;
    return {...step,target:{type:'power',lower,upper,unit:'W (estimate)'},effort:`${lower}–${upper} W (estimate)`};
  });
  return changed?{...definition,steps,reference_ftp_watts:ftp,effort_target:{...definition.effort_target,description:steps.map(step=>`${step.name??step.type}: ${step.effort}`).join('; ')}}:definition;
}

export function workoutEffortText(definition:PowerWorkout):string {
  return displayPower(definition).effort_target?.description??'';
}
