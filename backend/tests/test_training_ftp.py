import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from app.database import connect,migrate
from app.training_ftp import resolve


class FTPTests(unittest.TestCase):
 def test_verified_shapes_and_policy(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'test.sqlite';migrate(path)
   with connect(path) as c:
    # Resolver contract depends only on these retained columns; use a focused fixture view.
    c.execute('ALTER TABLE garmin_sync_payloads RENAME TO retained_payloads')
    c.execute('CREATE TABLE garmin_sync_payloads(data_type TEXT,payload_json TEXT,calendar_date TEXT)')
    record={'functionalThresholdPower':225,'sport':'CYCLING','calendarDate':'2026-06-11T14:13:21.355','isStale':False}
    def insert(value):
     c.execute("INSERT INTO garmin_sync_payloads VALUES('supplementary_metrics',?,'2026-10-15')",(json.dumps({'endpoints':{'get_cycling_ftp':value}}),))
    insert(record);result=resolve(c,date(2026,10,15));self.assertEqual(result['status'],'stale');self.assertEqual(result['measurement_date'],'2026-06-11')
    insert({**record,'calendarDate':'2026-10-10','functionalThresholdPower':250});self.assertEqual(resolve(c,date(2026,10,15))['watts'],250)
    insert({**record,'calendarDate':'2026-10-16','functionalThresholdPower':300});self.assertEqual(resolve(c,date(2026,10,15))['watts'],250)
    insert({**record,'sport':'RUNNING','calendarDate':'2026-10-14','functionalThresholdPower':400});self.assertEqual(resolve(c,date(2026,10,15))['watts'],250)
    insert({**record,'calendarDate':'2026-10-14','unit':'kW','functionalThresholdPower':400});self.assertEqual(resolve(c,date(2026,10,15))['watts'],250)
    c.execute('DELETE FROM garmin_sync_payloads');insert({**record,'calendarDate':None});self.assertEqual(resolve(c,date(2026,10,15))['status'],'undated')
