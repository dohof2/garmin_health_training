import {newDayNutrition} from './dailyChat.ts';
export function mergeNutritionContext(previous: Record<string,unknown>, result: Record<string,unknown>) {
  const next:Record<string,unknown>=result.context_date&&previous.day&&result.context_date!==previous.day?newDayNutrition(previous,String(result.context_date)):{...previous};
  if(result.context_date)next.day=result.context_date;
  if(result.chat_day)next.chat_day=result.chat_day;
  if(result.logged)delete next.pending_correction;
  else if('pending_correction' in result)next.pending_correction=result.pending_correction;
  if(Array.isArray(result.pending_drafts))next.pending_drafts=result.pending_drafts;
  if(result.target_saved)delete next.pending_target;
  else if(result.target_proposal && typeof result.target_proposal==='object') {
    next.pending_target=(result.target_proposal as {request?:unknown}).request??next.pending_target;
  }
  if(result.logged)next.pending_foods=[];
  else if(result.pending_foods_replaced&&Array.isArray(result.ingredients))next.pending_foods=result.ingredients;
  else if(Array.isArray(result.ingredients)&&result.ingredients.length) {
    const keys=['name','grams_low','grams_high','grams_proposed','question','meal_type','nutrients_per_100g','estimate_assumptions'];
    const key=(food:Record<string,unknown>)=>`${food.meal_type??'meal'}:${String(food.name??'').trim().toLocaleLowerCase()}`;
    const foods=new Map((Array.isArray(next.pending_foods)?next.pending_foods:[]).map(food=>[key(food),food]));
    for(const food of result.ingredients){const retained=Object.fromEntries(keys.filter(k=>k in food).map(k=>[k,food[k]]));foods.set(key(food),{...foods.get(key(food)),...retained});}
    next.pending_foods=[...foods.values()];
  }
  if(result.saved_meals)next.saved_meals=result.saved_meals;
  return next;
}

export function mergeNutritionEntry(previous: Record<string,unknown>, incoming: Record<string,unknown>) {
  // Merely opening the Nutrition page must not erase an active proposal.
  if(incoming.date_selected===false&&(previous.pending_correction||previous.pending_target||(Array.isArray(previous.pending_foods)&&previous.pending_foods.length)))incoming={...incoming,day:previous.day};
  const base=incoming.day&&previous.day&&incoming.day!==previous.day?newDayNutrition(previous,String(incoming.day)):previous;
  return {...base,...Object.fromEntries(Object.entries(incoming).filter(([key,value])=>
    value!==undefined && (!['pending_foods','draft_items'].includes(key)||!Array.isArray(value)||value.length>0)))};
}
