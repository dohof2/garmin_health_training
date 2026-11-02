export function chatDay(timeZone:string,now=new Date()) {
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 return ['year','month','day'].map(type=>parts.find(part=>part.type===type)!.value).join('-');
}
export function pendingDraft(context:Record<string,unknown>) {
 const pending=(Array.isArray(context.pending_foods)&&context.pending_foods.length>0)||Boolean(context.pending_correction);
 const target=Boolean(context.pending_target);
 if(!pending&&!target&&!(Array.isArray(context.draft_items)&&context.draft_items.length))return {};
 return Object.fromEntries(['day','chat_day','timezone','meal_type','pending_foods','pending_correction','pending_target','draft_items','date_selected'].filter(key=>context[key]!==undefined).map(key=>[key,context[key]]));
}
export function newDayNutrition(_context:Record<string,unknown>,day:string) {
 return {day};
}
export function persistPendingDraft(context:Record<string,unknown>) {
 try{const draft=pendingDraft(context);if(Object.keys(draft).length)localStorage.setItem('garmin-pending-nutrition-drafts-v1',JSON.stringify(draft));else localStorage.removeItem('garmin-pending-nutrition-drafts-v1');}catch{/* In-memory drafts remain usable. */}
}
