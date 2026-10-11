import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync('frontend/src/GraphCanvas.tsx','utf8');
const table=source.match(/const bands = (\{[\s\S]*?\n\});/)[1];
const fn=source.slice(source.indexOf('function rating('),source.indexOf('\nexport function Plot')).replace('value: number, profile?: Profile | null','value, profile');
class FixedDate extends Date { constructor(...args){super(...(args.length?args:['2026-10-11T12:00:00']));} }
const context=vm.createContext({Date:FixedDate});
vm.runInContext(`const bands=${table}; ${fn}; globalThis.rating=rating; globalThis.table=bands`,context);
const official={male:[[41.7,45.4,51.1,55.4],[40.5,44,48.3,54],[38.5,42.4,46.4,52.5],[35.6,39.2,43.4,48.9],[32.3,35.5,39.5,45.7],[29.4,32.3,36.7,42.1]],female:[[36.1,39.5,43.9,49.6],[34.4,37.8,42.4,47.4],[33,36.3,39.7,45.3],[30.1,33,36.7,41.1],[27.5,30,33,37.8],[25.9,28.1,30.9,36.7]]};
assert.deepEqual(JSON.parse(JSON.stringify(context.table)),official);
let checks=0;
const labels=['Poor','Fair','Good','Excellent','Superior'];
for(const sex of ['male','female']) for(let band=0;band<6;band++) for(let i=0;i<4;i++) for(const delta of [-0.001,0]){
 const profile={sex,birth_date:`${2026-(25+10*band)}-01-01`};
 const actual=context.rating(official[sex][band][i]+delta,profile);
 assert.equal(actual.text.split(' · ')[0],labels[i+(delta===0?1:0)]); checks++;
}
const profile={sex:'male',birth_date:'1985-12-31'};
const result={reference:'https://www8.garmin.com/manuals/webhelp/GUID-9183E86B-2399-4CFC-AB50-EAFC6D6ED326/EN-US/GUID-1FBCCD9E-19E1-4E4C-BD60-1793B5B97EB3.html',reference_tables_match:true,boundary_checks_passed:checks,current_example:context.rating(44.7,profile),same_position_for_distinct_values:[42.4,46.3].map(value=>({value,...context.rating(value,profile)})),age_convention:'Age calculated at rendering time, not measurement date',dial_convention:'Five equal category segments; pointer fixed at category midpoint'};
fs.writeFileSync('docs/qa/2026-10-11/vo2-audit.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
