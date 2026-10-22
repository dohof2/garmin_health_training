"""Launcher process ownership tests; no personal database or Garmin calls."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'local_app.py'
spec = importlib.util.spec_from_file_location('local_launcher', SCRIPT)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LocalLauncherTests(unittest.TestCase):
    def test_owned_process_stops(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        try:
            launcher.stop_process(process)
            self.assertIsNotNone(process.poll())
            launcher.stop_process(process)  # repeated cleanup is harmless
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_already_exited_process_is_harmless(self):
        process = subprocess.Popen([sys.executable, '-c', 'pass'], start_new_session=True)
        process.wait()
        launcher.stop_process(process)


if __name__ == '__main__':
    unittest.main()
