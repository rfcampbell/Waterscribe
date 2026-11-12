"""FEATURE_SCHEDULE hides every Schedule entry point; on, they come back. env_flag is pure; the page
tests need a throwaway DB (never prod):
WATERSCRIBE_TEST_DATABASE_URL=postgresql://.../ws_x venv/bin/python -m unittest tests.test_feature_schedule -v"""
import os
import re
import unittest
from datetime import datetime, timedelta
from unittest import mock

from app.config import env_flag

URL = os.environ.get('WATERSCRIBE_TEST_DATABASE_URL')


class EnvFlag(unittest.TestCase):
    def test_values(self):
        for raw, want in [(None, False), ('', False), ('false', False), ('0', False), ('no', False),
                          ('true', True), ('True', True), (' 1 ', True), ('yes', True), ('on', True)]:
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {} if raw is None else {'X_FLAG': raw}, clear=False):
                if raw is None:
                    os.environ.pop('X_FLAG', None)
                self.assertIs(env_flag('X_FLAG'), want)

    def test_default_is_off(self):
        from app.config import Config
        with mock.patch.dict(os.environ):
            os.environ.pop('FEATURE_SCHEDULE', None)
            self.assertFalse(env_flag('FEATURE_SCHEDULE'))
        self.assertIn('FEATURE_SCHEDULE', vars(Config))


# Every way into the Schedule feature from the UI
ENTRY_POINTS = {
    'tab button': re.compile(r"showTab\('schedule'\)"),
    'header task link': re.compile(r'href="#schedule"|navigateTab\(\'schedule\'\)'),
    'tab panel': re.compile(r'id="tab-schedule"'),
    'task form': re.compile(r'id="schedule-form"'),
    'header task count': re.compile(r'\d+ tasks? · next:|no tasks'),
}


@unittest.skipUnless(URL, 'set WATERSCRIBE_TEST_DATABASE_URL to a throwaway database')
class ScheduleFlag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.config import config
        config['default'].SQLALCHEMY_DATABASE_URI = URL
        from app import create_app, db
        from app.models import Aquarium, ScheduledTask
        cls.app, cls.db = create_app(), db
        cls.app.config['TESTING'] = True
        with cls.app.app_context():
            live = db.session.execute(db.text('select current_database()')).scalar()
            prod = (os.environ.get('DATABASE_URL') or '').rsplit('/', 1)[-1]
            if not live.startswith('ws_') or live == prod:
                raise RuntimeError(f'refusing to run: connected to {live!r}, not a ws_* throwaway database')
            tank = Aquarium(name='test-tank-sched', code='TSCH')
            db.session.add(tank)
            db.session.flush()
            db.session.add(ScheduledTask(aquarium_id=tank.id, task_name='Test filter rinse', frequency_days=7,
                                         next_due=datetime.now() + timedelta(days=2)))
            db.session.commit()
            cls.tank_id = tank.id
        cls.c = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        from app.models import Aquarium
        with cls.app.app_context():
            for a in Aquarium.query.filter_by(name='test-tank-sched'):
                cls.db.session.delete(a)   # cascades to its task
            cls.db.session.commit()

    def page(self, flag, path=None):
        self.app.config['FEATURE_SCHEDULE'] = flag
        r = self.c.get(path or f'/?aquarium_id={self.tank_id}')
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def test_off_hides_every_entry_point(self):
        html = self.page(False)
        for name, pat in ENTRY_POINTS.items():
            with self.subTest(name):
                self.assertIsNone(pat.search(html), name)
        self.assertNotIn('>Schedule<', html)
        self.assertNotIn('Test filter rinse', html)

    def test_on_restores_every_entry_point(self):
        html = self.page(True)
        for name, pat in ENTRY_POINTS.items():
            with self.subTest(name):
                self.assertIsNotNone(pat.search(html), name)
        self.assertIn('1 task · next: Test filter rinse', html)

    def test_manage_counts(self):
        off, on = self.page(False, '/aquariums'), self.page(True, '/aquariums')
        self.assertNotRegex(off, r'events, \d+ tasks, \d+ fish')
        self.assertRegex(on, r'events, \d+ tasks, \d+ fish')
        # deleting a tank still destroys its tasks, so the confirm keeps saying so when there are any
        self.assertRegex(off, r'1 tasks and 0 fish entries')

    def test_api_routes_still_reachable(self):
        self.app.config['FEATURE_SCHEDULE'] = False
        r = self.c.get(f'/api/aquarium/{self.tank_id}/scheduled')
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t['task_name'] for t in r.get_json()], ['Test filter rinse'])
        self.assertEqual(self.c.get(f'/api/aquarium/{self.tank_id}/stats').get_json()['upcoming_tasks'], 1)


if __name__ == '__main__':
    unittest.main()
