export type TimedStep={name?:string;type:string;duration_seconds?:number;repetitions?:number;effort?:string;target?:{type:string;lower:number;upper:number;unit:string};power_reference_fractions?:{lower:number;upper:number};steps?:TimedStep[]};
export function displaySteps(steps:TimedStep[],path:number[]=[],depth=0):Array<TimedStep&{duration_seconds:number;path:string}> {
 if(depth>5)return [];
 const output:Array<TimedStep&{duration_seconds:number;path:string}>=[];
 for(const [index,step] of steps.entries()) {
  const here=[...path,index+1],repeat=step.repetitions??1;
  if(!Number.isInteger(repeat)||repeat<1||repeat>50)return [];
  if(step.steps){const children=displaySteps(step.steps,here,depth+1);if(!children.length)return [];for(let i=0;i<repeat;i++)output.push(...children);}
  else if(typeof step.duration_seconds==='number'&&Number.isFinite(step.duration_seconds)&&step.duration_seconds>0)output.push({...step,duration_seconds:step.duration_seconds,path:here.join('.')});
  else return [];
  if(output.length>100)return [];
 }
 return output;
}
