import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mergeNutritionContext,mergeNutritionEntry,roleHistories} from '../src/chatContext.ts';

test('pending portions and nutrient estimates survive unrelated replies and opening nutrition',()=>{
 const food={name:'Rice',grams_low:150,grams_high:200,grams_proposed:180,nutrients_per_100g:{calories_kcal:130},estimate_assumptions:'Cooked'};
 const pending=mergeNutritionContext({}, {ingredients:[food],context_date:'2026-10-27'});
 assert.deepEqual(pending.pending_foods,[food]);
 assert.deepEqual(mergeNutritionContext(pending,{ingredients:[],reply:'That is a reasonable portion.'}).pending_foods,[food]);
 assert.deepEqual(mergeNutritionEntry(pending,{pending_foods:undefined,pending_target:undefined,draft_items:[]}).pending_foods,[food]);
 assert.deepEqual(mergeNutritionContext(pending,{logged:true,saved_meals:[{id:'saved',revision:1}]}).pending_foods,[]);
});
test('returning to trainer preserves its prior exchange across many nutrition messages',()=>{
 const messages:Array<{role:'user'|'assistant';content:string;chat_role?:string}>=[
  {role:'user',content:'I can train only Friday'},
  {role:'assistant',content:'We will use Friday',chat_role:'trainer'},
  ...Array.from({length:24},(_,i)=>({role:i%2?'assistant' as const:'user' as const,content:`Food turn ${i}`,chat_role:'nutrition'})),
 ];
 const history=roleHistories(messages);
 assert.equal(history.trainer[0].content,'I can train only Friday');
 assert.equal(history.trainer[1].content,'We will use Friday');
 assert.equal(history.trainer.at(-1)?.content,'Food turn 23');
 assert.ok(history.nutrition.length<=20);
});
test('saving a target clears only its proposal and retains food context',()=>{
 const result=mergeNutritionContext({pending_target:{goal:'maintain'},pending_foods:[{name:'Rice'}]}, {target_saved:true,ingredients:[]});
 assert.equal(result.pending_target,undefined);
 assert.deepEqual(result.pending_foods,[{name:'Rice'}]);
});
test('mixed task messages remain in both role histories after unrelated turns',()=>{
 const messages=[{role:'user' as const,content:'Make my ride easier; log my lunch',chat_roles:['trainer','nutrition']},{role:'assistant' as const,content:'Workout review and saved lunch',chat_role:'nutrition',chat_roles:['trainer','nutrition']},...Array.from({length:20},(_,i)=>({role:'user' as const,content:`Chart ${i}`,chat_role:'assistant'}))];
 const history=roleHistories(messages);
 assert.equal(history.trainer[0].content,'Make my ride easier; log my lunch');
 assert.equal(history.nutrition[1].content,'Workout review and saved lunch');
});
test('supper clarification retains the other meals',()=>{
 const previous={day:'2026-10-29',pending_foods:[{name:'Eggs',meal_type:'breakfast',grams_low:100},{name:'Rice',meal_type:'dinner',grams_low:150}]};
 const result=mergeNutritionContext(previous,{ingredients:[{name:'Rice',meal_type:'dinner',grams_low:220}]});
 assert.deepEqual(result.pending_foods,[{name:'Eggs',meal_type:'breakfast',grams_low:100},{name:'Rice',meal_type:'dinner',grams_low:220}]);
});
test('historical correction retains its chat day and pending action until committed',()=>{
 const pending={day:'2026-10-30',request:'Correct soup',candidates:[{meal_id:'meal',item_id:'soup'}]};
 const next=mergeNutritionContext({day:'2026-10-31'},{context_date:'2026-10-30',chat_day:'2026-10-31',pending_correction:pending,ingredients:[]});
 assert.deepEqual(next.pending_correction,pending);
 assert.equal(next.chat_day,'2026-10-31');
 const reopened=mergeNutritionEntry(next,{day:'2026-10-31',date_selected:false});
 assert.equal(reopened.day,'2026-10-30');
 assert.deepEqual(reopened.pending_correction,pending);
 assert.equal(mergeNutritionEntry(next,{day:'2026-10-31',date_selected:true}).pending_correction,undefined);
 const clarified=mergeNutritionContext(next,{context_date:'2026-10-30',pending_correction:{...pending,clarifications:['300 ml']}});
 assert.equal(clarified.chat_day,'2026-10-31');
 const saved=mergeNutritionContext(clarified,{logged:true,context_date:'2026-10-30',saved_meals:[{id:'meal',revision:2}]});
 assert.equal(saved.pending_correction,undefined);
 assert.deepEqual(saved.saved_meals,[{id:'meal',revision:2}]);
});
