"""Run the single-agent regression checks locally without remote model calls."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = ['test_skill_agent', 'test_native_agent_protocol', 'test_weekly_accounting', 'test_strength_set_requests', 'test_daily_chat_drafts',
         'test_nutrition_context_feedback', 'test_telegram_bot', 'test_route_matching',
         'test_maintenance', 'test_ai_providers', 'test_chatgpt_auth', 'test_database', 'test_nutrition']
TESTS += ['test_training_adjustments', 'test_training_coach', 'test_cycling_week',
          'test_advanced_cycling', 'test_power_tolerance', 'test_training_load_focus',
          'test_long_ride_allocation']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', action='store_true', help='Also build the UI and run frontend tests')
    args = parser.parse_args()
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(ROOT/'backend'), str(ROOT/'backend/tests')])}
    result = subprocess.run([sys.executable, '-m', 'unittest', *TESTS], cwd=ROOT, env=env)
    if result.returncode:
        return result.returncode
    if args.frontend:
        for command in (['npm','run','build'], ['node','--test','--experimental-strip-types',
                         *[str(p.relative_to(ROOT/'frontend')) for p in sorted((ROOT/'frontend/tests').glob('*.test.*'))]]):
            result = subprocess.run(command, cwd=ROOT/'frontend', env=env)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
