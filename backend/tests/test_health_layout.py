import tempfile
import unittest
from pathlib import Path
from app.database import migrate
from app.charts import read_layout,save_layout

class HealthLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.sqlite';migrate(self.path)
    def test_health_layout_does_not_overwrite_dashboard(self):
        dashboard=[{'id':'vo2','metric':'vo2_cycling','kind':'dial'}]
        health=[{'id':'weight','metric':'weight','kind':'line'}]
        save_layout(dashboard,self.path);save_layout(health,self.path,scope='health')
        self.assertEqual(read_layout(self.path),dashboard)
        self.assertEqual(read_layout(self.path,scope='health'),health)
        save_layout([],self.path,scope='health')
        self.assertEqual(read_layout(self.path,scope='health'),[])
        self.assertEqual(read_layout(self.path),dashboard)
    def test_scope_and_specs_are_validated(self):
        with self.assertRaises(ValueError):read_layout(self.path,scope='other')
        with self.assertRaises(ValueError):save_layout([],self.path,scope='other')
        with self.assertRaises(ValueError):save_layout([{'id':'bad','metric':'fake','kind':'line'}],self.path,scope='health')
        self.assertIsNone(read_layout(self.path,scope='health'))
