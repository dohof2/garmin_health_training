"""Acceptance regressions for numerical correctness and conversational choices."""
import json
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch

from app.database import connect,migrate
from app.plot_requests import period
from app.ai_tools import execute_tool


class AssistantRobustness(unittest.TestCase):
    def setUp(self):
        calendar_patch=patch('app.ride_comparison.date',wraps=date)
        calendar=calendar_patch.start();calendar.today.return_value=date(2026,10,11)
        self.addCleanup(calendar_patch.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'qa.sqlite3';migrate(self.path)
        with connect(self.path) as c:
            for metric in ['body_battery_latest','sleep_score']:
                c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,'garmin_connect',?,'2026-10-09',75,'score')",(metric,metric))
            for i in range(1,8):
                c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES(?,'garmin_connect','steps',?,?,'steps')",(str(i),f'2026-10-{i+4:02}',100*i))
            c.execute("INSERT INTO metric_readings(id,source_name,metric_type,recorded_at,value,unit) VALUES('fake','synthetic_fixture','steps','2026-10-11',999999,'steps')")
            for identifier,day,kind,distance in [('ride','2026-10-09','mountain_biking',30000),('older','2026-09-01','cycling',10000),('old','2025-09-01','cycling',50000),('hike','2026-10-10','hiking',5000)]:
                c.execute("INSERT INTO activities(id,source_name,name,activity_type,started_at,distance_meters) VALUES(?,'garmin_connect',?,?,?,?)",(identifier,identifier,kind,day+'T10:00:00Z',distance))


    def test_recorded_volume_excludes_empty_weeks_and_requires_complete_durations(self):
        from app.ride_comparison import riding_volume_context
        anchor=date(2026,10,9)
        rides=[{'local_date':anchor.isoformat(),'duration_seconds':7200}]
        for week,hours in enumerate([1,2,3,4],1):
            rides.append({'local_date':(anchor-timedelta(days=7*week)).isoformat(),'duration_seconds':hours*3600})
        result=riding_volume_context(rides,rides[0])
        self.assertEqual(result['comparison_week_count'],4)
        self.assertEqual(result['recent_middle_range_hours'],[1.75,3.25])
        self.assertEqual(result['position'],'within')
        self.assertIn('prior weeks with rides',result['interpretation'])
        rides[-1]['duration_seconds']=None
        self.assertIsNone(riding_volume_context(rides,rides[0])['interpretation'])
        rides[-1]['duration_seconds']=14400;rides[0]['duration_seconds']=None
        self.assertIsNone(riding_volume_context(rides,rides[0])['interpretation'])

    def test_multiple_training_commitments_preserve_days_and_do_not_invent_duration(self):
        from app.training_coach import parse_request,validate_brief
        brief,recognized=parse_request('I want two hard rides Tuesday and wedensday. Long ride on firday and I can train today. I want FTP improvement.',validate_brief({}),date(2026,10,12))
        events={e['date']:e for e in brief['fixed_events']}
        self.assertEqual(set(events),{'2026-10-13','2026-10-14','2026-10-16'})
        self.assertEqual(events['2026-10-13']['effort'],'hard')
        self.assertEqual(events['2026-10-14']['effort'],'hard')
        self.assertTrue(all(e['duration_minutes'] is None for e in events.values()))
        self.assertTrue(any('today is separate' in r for r in recognized))
        self.assertEqual(brief['goal'],'ftp')

    def test_training_duration_and_effort_stay_with_their_own_clause(self):
        from app.training_coach import parse_request,validate_brief
        brief,_=parse_request('Hard ride Tuesday for 3.5 hours and easy ride Friday for 45 minutes.',validate_brief({}),date(2026,10,12))
        events={e['date']:e for e in brief['fixed_events']}
        self.assertEqual((events['2026-10-13']['duration_minutes'],events['2026-10-13']['effort']),(210,'hard'))
        self.assertEqual((events['2026-10-16']['duration_minutes'],events['2026-10-16']['effort']),(45,'easy'))
