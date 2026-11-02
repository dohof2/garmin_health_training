import assert from 'node:assert/strict';
import {test} from 'node:test';
import {chatDay,newDayNutrition,pendingDraft} from '../src/dailyChat.ts';
test('daily boundary uses the selected timezone',()=>{
 assert.equal(chatDay('Asia/Jerusalem',new Date('2026-10-28T22:30:00Z')),'2026-10-29');
 assert.equal(chatDay('UTC',new Date('2026-10-28T22:30:00Z')),'2026-10-28');
});
test('new day discards every pending request and old reference',()=>{
 const next=newDayNutrition({day:'2026-10-27',pending_foods:[{name:'Rice'}],pending_drafts:[{day:'2026-10-26'}],pending_target:{goal:'maintain'},saved_meals:[{id:'old'}]},'2026-10-29');
 assert.deepEqual(next,{day:'2026-10-29'});assert.deepEqual(pendingDraft(next),{});
});
