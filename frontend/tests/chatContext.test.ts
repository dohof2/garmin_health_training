import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mergeNutritionContext,mergeNutritionEntry} from '../src/chatContext.ts';

test('pending portions and nutrient estimates survive unrelated replies and opening nutrition',()=>{
 const food={name:'Rice',grams_low:150,grams_high:200,grams_proposed:180,nutrients_per_100g:{calories_kcal:130},estimate_assumptions:'Cooked'};
 const pending=mergeNutritionContext({}, {ingredients:[food],context_date:'2026-10-27'});
 assert.deepEqual(pending.pending_foods,[food]);
 assert.deepEqual(mergeNutritionContext(pending,{ingredients:[],reply:'That is a reasonable portion.'}).pending_foods,[food]);
 assert.deepEqual(mergeNutritionEntry(pending,{pending_foods:undefined,pending_target:undefined,draft_items:[]}).pending_foods,[food]);
 assert.deepEqual(mergeNutritionContext(pending,{logged:true,saved_meals:[{id:'saved',revision:1}]}).pending_foods,[]);
});

test('saving a target clears only its proposal and retains food context',()=>{
 const result=mergeNutritionContext({pending_target:{goal:'maintain'},pending_foods:[{name:'Rice'}]}, {target_saved:true,ingredients:[]});
 assert.equal(result.pending_target,undefined);
 assert.deepEqual(result.pending_foods,[{name:'Rice'}]);
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
