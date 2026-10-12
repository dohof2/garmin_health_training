import tempfile
import unittest
from datetime import datetime, timedelta, UTC
from pathlib import Path
from app.database import connect, migrate
from app.charts import chart_data, validate_spec, save_layout, read_layout
from app.ai_tools import execute_tool
from app.ai_chat import _execute_calls


class ActivityStreamChartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite'
        migrate(self.path)
        self.origin = datetime(2026, 10, 10, 22, 50, tzinfo=UTC)
        self.add('a', [(0, 0), (1, 200), (2, None), (3, 220), (4, 240), (10, 400)])
        self.add('b', [(0, 150), (1, 180), (2, 210)], shift=40, kind='virtual_ride')
        self.spec = {'metric': 'stream:power', 'kind': 'line', 'x_metric': 'elapsed_time', 'activity_ids': ['a', 'b'], 'timezone': 'Asia/Jerusalem'}

    def add(self, identifier, samples, shift=0, source='garmin_connect', deleted=False, kind='indoor_cycling'):
        origin = self.origin + timedelta(seconds=shift)
        with connect(self.path) as c:
            c.execute('INSERT INTO activities(id,source_name,name,activity_type,started_at,deleted_at) VALUES(?,?,?,?,?,?)', (identifier, source, 'Invented ' + identifier, kind, origin.isoformat(), '2026-10-11' if deleted else None))
            for second, power in samples:
                c.execute('INSERT INTO activity_samples(activity_id,recorded_at,power_watts,heart_rate_bpm,cadence_rpm,speed_mps) VALUES(?,?,?,?,?,?)', (identifier, (origin + timedelta(seconds=second)).isoformat(), power, 120, 80, 10))

    def test_overlay_aligns_separate_recordings_and_preserves_zero(self):
        result = chart_data(self.spec, self.path)
        self.assertEqual([s['id'] for s in result['series']], ['a', 'b'])
        self.assertEqual(result['count'], 8)
        first = [p for p in result['points'] if p['series_id'] == 'a']
        second = [p for p in result['points'] if p['series_id'] == 'b']
        self.assertEqual((first[0]['x'], second[0]['x']), (0, 0))
        self.assertEqual(first[0]['y'], 0)
        self.assertEqual(result['x_unit'], 's')
        self.assertEqual(result['series'][0]['maximum'], 400)
        self.assertNotEqual(result['series'][0]['color'], result['series'][1]['color'])

    def test_nulls_and_long_gaps_break_lines_without_interpolation(self):
        result = chart_data(self.spec, self.path)
        points = [p for p in result['points'] if p['id'] == 'a']
        self.assertEqual([p['x'] for p in points], [0, 1, 3, 4, 10])
        self.assertEqual([p['segment'] for p in points], [0, 0, 1, 1, 2])
        self.assertEqual((result['excluded'], result['series'][0]['gap_count']), (1, 2))

    def test_date_selection_uses_local_activity_start_and_includes_virtual_rides(self):
        spec = {k: v for k, v in self.spec.items() if k != 'activity_ids'}
        result = chart_data({**spec, 'start': '2026-10-11', 'end': '2026-10-11', 'sport': 'cycling'}, self.path)
        self.assertEqual([s['id'] for s in result['series']], ['a', 'b'])
        self.assertTrue(all(p['date'] == '2026-10-11' for p in result['points']))
        self.assertEqual(chart_data({**spec, 'start': '2026-10-10', 'end': '2026-10-10'}, self.path)['count'], 0)

    def test_synthetic_deleted_and_unknown_recordings_cannot_enter_overlay(self):
        self.add('synthetic', [(0, 9999)], source='synthetic_fixture')
        self.add('deleted', [(0, 8888)], deleted=True)
        for identifier in ('synthetic', 'deleted', 'unknown'):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                chart_data({**self.spec, 'activity_ids': ['a', identifier]}, self.path)
        result = chart_data({'metric': 'stream:power', 'kind': 'line', 'start': '2026-10-11', 'end': '2026-10-11', 'timezone': 'Asia/Jerusalem'}, self.path)
        self.assertEqual({s['id'] for s in result['series']}, {'a', 'b'})

    def test_invalid_chart_scope_and_summary_settings_are_rejected(self):
        for changes in ({'activity_ids': ['a', 'a']}, {'activity_ids': []}, {'activity_ids': 'a'}, {'activity_ids': [None]}, {'kind': 'scatter'}, {'x_metric': 'date'}, {'trend_line': True}, {'correlation': True}, {'aggregation': 'daily_mean'}, {'rolling_days': 7}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                chart_data({**self.spec, **changes}, self.path)
        with self.assertRaises(ValueError):
            validate_spec({'metric': 'stream:power', 'kind': 'line'}, self.path)
        with self.assertRaises(ValueError):
            validate_spec({**self.spec, 'metric': 'activity_power'}, self.path)

    def test_more_than_eight_recordings_requests_narrower_scope(self):
        for index in range(7): self.add(f'extra-{index}', [(0, 100)])
        with self.assertRaisesRegex(ValueError, '9 activities match'):
            chart_data({'metric': 'stream:power', 'kind': 'line', 'start': '2026-10-11', 'end': '2026-10-11', 'timezone': 'Asia/Jerusalem'}, self.path)

    def test_reduction_keeps_peaks_endpoints_and_gap_boundaries(self):
        samples = [(i, 9999 if i == 1234 else 100) for i in range(6001)]
        self.add('long', samples)
        result = chart_data({**self.spec, 'activity_ids': ['long']}, self.path)
        self.assertEqual(result['count'], 6001)
        self.assertLess(len(result['points']), 6001)
        self.assertEqual((result['points'][0]['x'], result['points'][-1]['x']), (0, 6000))
        self.assertEqual(max(p['y'] for p in result['points']), 9999)
        self.assertEqual({p['segment'] for p in result['points']}, {0})
        self.assertIn('display reduced', ' '.join(result['notes']))

    def test_missing_stream_retains_label_without_inventing_values(self):
        self.add('empty', [(0, None), (1, None)])
        result = chart_data({**self.spec, 'activity_ids': ['a', 'empty']}, self.path)
        self.assertEqual(result['series'][1]['count'], 0)
        self.assertIsNone(result['series'][1]['mean'])
        self.assertFalse(any(p['id'] == 'empty' for p in result['points']))
        self.assertIn('no trace can be drawn', ' '.join(result['notes']))

    def test_other_recorded_metrics_and_speed_conversion(self):
        for metric, expected, unit in [('stream:heart_rate', 120, 'bpm'), ('stream:cadence', 80, 'rpm'), ('stream:speed', 36, 'km/h')]:
            result = chart_data({**self.spec, 'metric': metric}, self.path)
            self.assertEqual({p['y'] for p in result['points']}, {expected})
            self.assertEqual(result['unit'], unit)

    def test_tool_and_pinned_graph_keep_same_activity_ids(self):
        result = execute_tool('create_plots', {'plots': [self.spec]}, self.path)
        self.assertEqual(len(result['plots'][0]['series']), 2)
        spec = {**result['plots'][0]['spec'], 'id': 'pin'}
        save_layout([spec], self.path)
        self.assertEqual(read_layout(self.path)[0]['activity_ids'], ['a', 'b'])
        self.assertEqual(chart_data(read_layout(self.path)[0], self.path)['count'], 8)

    def test_model_receives_summary_and_ui_receives_complete_trace(self):
        outputs, evidence = _execute_calls([('overlay', 'create_plots', {'plots': [self.spec]})], self.path, message='Overlay two recordings', timezone_name='Asia/Jerusalem', model_driven=True)
        import json
        model = json.loads(outputs[0]['serialized'])
        self.assertNotIn('points', model['plots'][0])
        self.assertEqual(model['plots'][0]['series'][0]['maximum'], 400)
        self.assertEqual(len(evidence[0]['plots'][0]['points']), 8)

    def test_fragmented_display_is_bounded_without_joining_gaps(self):
        self.add('fragmented', [(i * 10, 9000 if i == 1234 else 100) for i in range(6001)])
        result = chart_data({**self.spec, 'activity_ids': ['fragmented']}, self.path)
        self.assertEqual(result['count'], 6001)
        self.assertLessEqual(len(result['points']), 2000)
        self.assertEqual(len({p['segment'] for p in result['points']}), len(result['points']))
        self.assertEqual(max(p['y'] for p in result['points']), 9000)
        self.assertEqual((result['points'][0]['x'], result['points'][-1]['x']), (0, 60000))
