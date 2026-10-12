import tempfile
import unittest
from pathlib import Path
from app.database import connect,migrate
from app.activity_removal import set_removed,removed_activities
from app.history import list_activities,get_activity,history_summary
from app.charts import chart_data
from app.sync import _upsert_activity

class ActivityRemovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
        with connect(self.path) as c:
            c.execute("INSERT INTO activities(id,source_name,source_record_id,name,activity_type,started_at,duration_seconds,raw_json) VALUES('ride','garmin_connect','123','Invented ride','cycling','2026-10-11T10:00:00Z',3600,'{}')")
            c.execute("INSERT INTO activity_samples(activity_id,recorded_at,power_watts) VALUES('ride','2026-10-11T10:00:00Z',180)")
    def test_remove_excludes_history_detail_and_charts_but_preserves_data(self):
        set_removed('ride',True,self.path)
        self.assertEqual(list_activities(path=self.path),[])
        self.assertIsNone(get_activity('ride',path=self.path))
        self.assertEqual(history_summary(path=self.path)['activity_count'],0)
        self.assertEqual(chart_data({'metric':'activity_duration','kind':'line'},self.path)['points'],[])
        self.assertEqual(len(removed_activities(self.path)),1)
        with connect(self.path) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM activity_samples').fetchone()[0],1)
    def test_restore_and_idempotent_remove(self):
        set_removed('ride',True,self.path);stamp=removed_activities(self.path)[0]['locally_removed_at']
        set_removed('ride',True,self.path);self.assertEqual(removed_activities(self.path)[0]['locally_removed_at'],stamp)
        set_removed('ride',False,self.path);set_removed('ride',False,self.path)
        self.assertEqual(len(list_activities(path=self.path)),1);self.assertEqual(removed_activities(self.path),[])
    def test_sync_cannot_resurrect_local_removal(self):
        set_removed('ride',True,self.path)
        with connect(self.path) as c:
            _upsert_activity(c,{'source_record_id':'123','activity_type':'cycling','name':'Refreshed ride','started_at':'2026-10-11T10:00:00Z','duration_seconds':3600})
            self.assertIsNotNone(c.execute("SELECT deleted_at FROM activities WHERE id='ride'").fetchone()[0])
        self.assertEqual(list_activities(path=self.path),[])
        set_removed('ride',False,self.path);self.assertEqual(len(list_activities(path=self.path)),1)
    def test_unknown_synthetic_and_invalid_boolean(self):
        with self.assertRaises(LookupError):set_removed('missing',True,self.path)
        with self.assertRaises(ValueError):set_removed('ride','yes',self.path)
        with connect(self.path) as c:c.execute("UPDATE activities SET source_name='synthetic_fixture' WHERE id='ride'")
        with self.assertRaises(LookupError):set_removed('ride',True,self.path)
    def test_source_deleted_activity_is_not_restored_by_local_api(self):
        with connect(self.path) as c:c.execute("UPDATE activities SET deleted_at='2026-10-12' WHERE id='ride'")
        with self.assertRaises(ValueError):set_removed('ride',True,self.path)
        set_removed('ride',False,self.path);self.assertEqual(list_activities(path=self.path),[])
