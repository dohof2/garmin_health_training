from __future__ import annotations

import unittest

from app.xml_activity_import import parse_activity_xml


class XmlActivityImportTests(unittest.TestCase):
    def test_parses_gpx_points_and_extensions(self) -> None:
        document = b"""<?xml version='1.0'?>
        <gpx xmlns='http://www.topografix.com/GPX/1/1'>
          <trk><trkseg>
            <trkpt lat='32.0' lon='34.0'><ele>10</ele><time>2025-01-01T06:00:00Z</time></trkpt>
            <trkpt lat='32.001' lon='34.001'><ele>12</ele><time>2025-01-01T06:01:00Z</time>
              <extensions><hr>150</hr><cad>80</cad><power>200</power></extensions>
            </trkpt>
          </trkseg></trk>
        </gpx>"""
        parsed = parse_activity_xml(document, "gpx")
        self.assertEqual(len(parsed["points"]), 2)
        self.assertEqual(parsed["session"]["total_timer_time"], 60)
        self.assertGreater(parsed["session"]["total_distance"], 0)
        self.assertEqual(parsed["points"][1]["heart_rate"], 150)

    def test_rejects_xml_entities(self) -> None:
        document = b"<!DOCTYPE gpx [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><gpx/>"
        with self.assertRaises(ValueError):
            parse_activity_xml(document, "gpx")


if __name__ == "__main__":
    unittest.main()
