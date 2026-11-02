import assert from 'node:assert/strict';
import {test} from 'node:test';
import {formatChatDurations} from '../src/chatDuration.ts';

test('threshold ride efforts and recovery use minutes:seconds', () => {
  assert.equal(formatChatDurations('Two 480-second efforts at 227 W and 229 W, separated by a 240-second recovery.'),
    'Two 8:00 efforts at 227 W and 229 W, separated by a 4:00 recovery.');
});
test('hour durations use hours:minutes:seconds, including exact hour boundary', () => {
  assert.equal(formatChatDurations('3599 seconds, 3600 seconds, 4080 seconds, 7325 sec.'),
    '59:59, 1:00:00, 1:08:00, 2:02:05.');
});
test('preserves fractional seconds, short efforts, existing times and other units', () => {
  assert.equal(formatChatDurations('61.50 seconds; 30-second sprint; 8:00; 34 hours; 480 W; 480 milliseconds.'),
    '1:01.5; 30-second sprint; 8:00; 34 hours; 480 W; 480 milliseconds.');
});
test('preserves code, URLs, rates and signed values', () => {
  const text='`480 seconds` ```480 seconds``` https://example.com/480-seconds 120 seconds/day -120 seconds';
  assert.equal(formatChatDurations(text), text);
});
