import assert from 'node:assert/strict';
import {mkdir, mkdtemp, rm, readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {rolldown} from 'rolldown';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

// Render the real chat restoration path, including the evidence and Save card.
const root = fileURLToPath(new URL('../', import.meta.url));
await mkdir(`${root}node_modules/.cache`, {recursive: true});
const temporary = await mkdtemp(`${root}node_modules/.cache/chat-render-`);
try {
  const build = await rolldown({
    input: `${root}src/App.tsx`,
    platform: 'node',
    external: ['react', 'react/jsx-runtime'],
    transform: {jsx: 'react-jsx'},
  });
  await build.write({dir: temporary, format: 'esm'});
  await build.close();
  const {default: App, restoreChatReceipt} = await import(`${temporary}/App.js`);
  const saved = new Map();
  globalThis.sessionStorage = globalThis.localStorage = {
    getItem: key => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
  };
  globalThis.window = {location: {hash: '#dashboard'}};
  const catalog = {
    tool: 'get_garmin_strength_catalog',
    records: [{name: 'Calf Raise', category: 'CALF_RAISE', exercise: 'CALF_RAISE',
      planning_metadata: {equipment: 'bodyweight'}}],
  };
  const proposal = {
    tool: 'propose_training_adjustment',
    training_adjustment: {
      kind: 'adaptation', status: 'proposal', message: 'Add 2 sets of calf raises.',
      request: 'Add 2 sets of calf raises', fingerprint: 'test',
      adjustments: ['2026-11-05', '2026-11-10', '2026-11-12'].map(date => ({
        workout_id: date, date, title: 'Strength', summary: ['Calf Raise: 2 sets'],
        changes: {definition: {title: 'Strength', duration_minutes: 29}},
      })),
    },
  };
  function render(evidence) {
    saved.set('garmin-shared-chat-v1', JSON.stringify([{
      id: 'calf-raise-review', role: 'assistant', content: 'Review your calf raises.', evidence,
    }]));
    return renderToStaticMarkup(createElement(App));
  }
  const recovered = restoreChatReceipt({id: 'restore', role: 'assistant', content: '', evidence: [catalog]}, [
    {type: 'tool', evidence: catalog}, {type: 'tool', evidence: proposal},
    {type: 'delta', text: 'Your proposal is ready.'}, {type: 'complete', workflow: 'skills'},
  ]);
  assert.equal(recovered.content, 'Your proposal is ready.');
  assert.equal(recovered.evidence.length, 2);
  saved.set('garmin-shared-chat-v1', JSON.stringify([recovered]));
  assert.match(renderToStaticMarkup(createElement(App)), /Save training change/);
  assert.match(restoreChatReceipt(recovered, [{type: 'error', message: 'Interrupted; results retained.'}]).content, /Interrupted/);
  const html = render([catalog, proposal]);
  assert.match(html, /Calf Raise · calf raise · bodyweight/);
  assert.match(html, /Save training change/);
  for (const day of ['2026-11-05', '2026-11-10', '2026-11-12']) assert.match(html, new RegExp(day));
  assert.doesNotMatch(html, /Date unavailable|Invalid Date/);
  for (const local_date of [undefined, '', 'invalid', '2026-02-30']) {
    const markup = render([{tool: 'lookup_activities', records: [{name: 'Ride', local_date}, {}]}]);
    assert.match(markup, /Ride/);
    assert.doesNotMatch(markup, /Invalid Date/);
  }
  const activity = render([{tool: 'lookup_activities', records: [{id: 'ride', activity_type: 'road_biking',
    local_date: '2026-11-04', similarity_score: 91, route_overlap_percent: 82}]}]);
  assert.match(activity, /road biking/);
  assert.match(activity, /91% similarity/);
  assert.match(activity, /82% route overlap/);
  if (process.env.CHAT_EVENTS_FILE) {
    const events = JSON.parse(await readFile(process.env.CHAT_EVENTS_FILE, 'utf8'));
    const message = {id: 'real-receipt', role: 'assistant', content: '', evidence: []};
    for (const event of events) {
      if (event.type === 'tool') message.evidence.push(event.evidence);
      if (event.type === 'delta') message.content += event.text;
      if (event.type === 'complete') Object.assign(message, {usage: event.usage, workflow: event.workflow});
      saved.set('garmin-shared-chat-v1', JSON.stringify([message]));
      renderToStaticMarkup(createElement(App));
    }
    console.log('Passed: every event in actual chat receipt.');
  }
  console.log('Passed: restored calf-raise catalog and 3-workout Save proposal; absent/invalid dates; activity evidence.');
} finally {
  await rm(temporary, {recursive: true, force: true});
}
