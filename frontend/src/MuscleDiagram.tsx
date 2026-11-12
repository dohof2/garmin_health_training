import {muscleNames,muscleProfile,type Muscle,type MuscleProfile} from './exerciseMuscles';

const front:Partial<Record<Muscle,string[]>>={
 shoulders:['M35 44 Q24 43 25 63 L35 65 41 50Z'],
 chest:['M41 49 Q49 45 58 49 L58 66 Q48 74 37 62Z'],
 biceps:['M27 65 Q33 63 34 72 L27 91 21 88Z'],
 forearms:['M21 92 L27 95 17 119 11 118Z'],
 abs:['M48 75 L58 74 58 84 48 84Z','M48 87 L58 87 58 97 48 97Z','M49 100 L58 100 58 112 51 112Z'],
 obliques:['M38 72 L46 77 46 105 39 115 36 100Z'],
 quads:['M39 128 Q44 123 55 128 L55 153 49 178 40 174 36 150Z'],
 calves:['M40 191 L49 191 47 214 43 231 38 224Z'],
};
const back:Partial<Record<Muscle,string[]>>={
 upper_back:['M47 41 L58 38 58 71 46 65 37 52Z'],
 shoulders:['M35 44 Q24 43 25 63 L35 65 41 50Z'],
 lats:['M37 64 L46 68 57 75 51 102 40 95Z'],
 lower_back:['M52 86 L58 80 58 116 49 115Z'],
 triceps:['M27 65 Q33 63 34 72 L27 91 21 88Z'],
 forearms:['M21 92 L27 95 17 119 11 118Z'],
 glutes:['M39 116 Q50 111 58 119 L58 137 Q46 145 37 132Z'],
 hamstrings:['M39 142 L55 142 53 163 49 181 40 176 37 156Z'],
 calves:['M40 188 Q51 187 50 203 L46 224 40 226 36 207Z'],
};
const silhouette='M52 35 L68 35 70 41 Q91 40 96 58 L105 87 115 118 111 128 104 125 99 106 87 80 84 98 86 121 Q92 139 88 167 L83 188 85 215 80 246 88 253 86 258 70 258 68 246 70 215 67 188 61 151 59 151 53 188 50 215 52 246 50 258 34 258 32 253 40 246 35 215 37 188 32 167 Q28 139 34 121 L36 98 33 80 21 106 16 125 9 128 5 118 15 87 24 58 Q29 40 50 41Z';

export default function MuscleDiagram({exerciseId,name,profile:supplied}:{exerciseId?:string;name:string;profile?:MuscleProfile}) {
 const profile=supplied??muscleProfile(exerciseId,name);
 if(!profile)return <small className="graph-meta">Muscle illustration is not yet available for this exercise.</small>;
 const colour=(muscle:Muscle)=>profile.primary.includes(muscle)?'#e84949':profile.secondary.includes(muscle)?'#f3cd43':'#cbd2da';
 return <figure className="muscle-diagram">
  <svg viewBox="0 0 250 284" role="img" aria-label={`${name}: front and back muscle diagram. Primary: ${profile.primary.map(m=>muscleNames[m]).join(', ')}. Supporting: ${profile.secondary.map(m=>muscleNames[m]).join(', ')||'none highlighted'}.`}>
   {[front,back].map((regions,index)=><g key={index} transform={`translate(${index*130},0)`}>
    <circle cx="60" cy="20" r="13" fill="#dfe4e9" stroke="#87939e"/>
    <path d={silhouette} fill="#e4e8ed" stroke="#87939e" strokeWidth="1"/>
    {Object.entries(regions).map(([muscle,paths])=><g key={muscle} fill={colour(muscle as Muscle)} stroke="#fff" strokeWidth=".8"><title>{muscleNames[muscle as Muscle]}</title>{[false,true].flatMap(mirror=>(paths??[]).map((d,i)=><path key={`${mirror}-${i}`} d={d} transform={mirror?'translate(120,0) scale(-1,1)':undefined}/>))}</g>)}
    <text x="60" y="278" textAnchor="middle" fill="currentColor" fontSize="11">{index===0?'Front':'Back'}</text>
   </g>)}
  </svg>
  <figcaption><span className="muscle-primary">Primary</span>: {profile.primary.map(m=>muscleNames[m]).join(', ')}{profile.secondary.length>0&&<><br/><span className="muscle-secondary">Supporting</span>: {profile.secondary.map(m=>muscleNames[m]).join(', ')}</>}</figcaption>
 </figure>;
}
