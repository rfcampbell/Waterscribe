"""check_tasks.py respects FEATURE_SCHEDULE. No DB, no Slack: the "on" case is given empty credentials
so it stops at its own missing-config check. venv/bin/python -m unittest tests.test_check_tasks -v"""
import os
import subprocess
import sys
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'check_tasks.py')


def run(**env):
    # explicit env wins over .env (the script only setdefaults from it)
    e = {k: v for k, v in os.environ.items() if k not in ('FEATURE_SCHEDULE', 'SLACK_BOT_TOKEN', 'DATABASE_URL')}
    e.update(env)
    return subprocess.run([sys.executable, SCRIPT], env=e, capture_output=True, text=True, timeout=30)


class CheckTasksFlag(unittest.TestCase):
    # credentials that would fail loudly if the script tried to use them
    TRAP = {'SLACK_BOT_TOKEN': 'xoxb-not-a-token', 'DATABASE_URL': 'postgresql://nobody@127.0.0.1:1/ws_none'}

    def test_off_exits_quietly_with_one_line(self):
        for flag in ('false', '0', ''):
            with self.subTest(flag=flag):
                r = run(FEATURE_SCHEDULE=flag, **self.TRAP)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout, 'FEATURE_SCHEDULE is off; not checking scheduled tasks\n')
                self.assertEqual(r.stderr, '')

    def test_on_goes_past_the_gate(self):
        r = run(FEATURE_SCHEDULE='true', SLACK_BOT_TOKEN='', DATABASE_URL='')
        self.assertEqual(r.returncode, 1)
        self.assertIn('Missing SLACK_BOT_TOKEN or DATABASE_URL', r.stderr)
        self.assertNotIn('FEATURE_SCHEDULE is off', r.stdout)


if __name__ == '__main__':
    unittest.main()
