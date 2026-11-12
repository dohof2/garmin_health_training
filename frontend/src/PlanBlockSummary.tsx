export type PlanBlock={week:number;starts_on:string;phase:string;focus:string};
type BlockRange={phase:string;start:string;end:string;focus:string};
export function planBlockRanges(blocks:PlanBlock[],endsOn:string):BlockRange[] {
  const sorted=[...blocks].sort((a,b)=>a.starts_on.localeCompare(b.starts_on));
  const grouped:BlockRange[]=[];
  for(const block of sorted){
    const end=new Date(`${block.starts_on}T12:00:00Z`);end.setUTCDate(end.getUTCDate()+6);
    const finish=[end.toISOString().slice(0,10),endsOn].sort()[0];
    const last=grouped.at(-1),next=new Date(`${last?.end??block.starts_on}T12:00:00Z`);next.setUTCDate(next.getUTCDate()+1);
    if(last?.phase===block.phase&&next.toISOString().slice(0,10)===block.starts_on)last.end=finish;
    else grouped.push({phase:block.phase,start:block.starts_on,end:finish,focus:block.focus});
  }
  return grouped;
}
export default function PlanBlockSummary({blocks,endsOn,today}:{blocks:PlanBlock[];endsOn:string;today:string}) {
  const ranges=planBlockRanges(blocks,endsOn),current=ranges.find(b=>b.start<=today&&b.end>=today),next=ranges.find(b=>b.start>today);
  const date=(day:string)=>new Date(`${day}T12:00:00Z`).toLocaleDateString(undefined,{timeZone:'UTC',month:'short',day:'numeric',year:'numeric'});
  const focus=current?blocks.find(b=>b.starts_on<=today&&new Date(`${b.starts_on}T12:00:00Z`).getTime()+7*86400000>new Date(`${today}T12:00:00Z`).getTime())?.focus:undefined;
  return <section className="journal-plan-blocks" aria-label="Current and next training blocks">{[{label:'Current block',block:current},{label:'Next block',block:next}].map(({label,block})=><article key={label}><p className="journal-kicker">{label}</p>{block?<><h3>{block.phase}</h3><p className="journal-block-dates"><time dateTime={block.start}>{date(block.start)}</time> – <time dateTime={block.end}>{date(block.end)}</time></p><p>{label==='Current block'?(focus??block.focus):block.focus}</p></>:<p>{label==='Current block'?'No block scheduled for today.':'This is the final scheduled block.'}</p>}</article>)}</section>;
}
