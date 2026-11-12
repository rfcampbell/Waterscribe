"""Target ranges, tank order and the remembered tank. Needs a throwaway DB (never prod):
WATERSCRIBE_TEST_DATABASE_URL=postgresql://.../ws_xxx venv/bin/python -m unittest tests.test_targets -v"""
import os
import unittest

URL = os.environ.get('WATERSCRIBE_TEST_DATABASE_URL')


@unittest.skipUnless(URL, 'set WATERSCRIBE_TEST_DATABASE_URL to a throwaway database')
class Targets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # same guard as test_tank_code: config is read at import, so set it on the class and check
        from app.config import config
        config['default'].SQLALCHEMY_DATABASE_URI = URL
        from app import create_app, db
        from app.models import Aquarium, TargetRange
        cls.app, cls.db, cls.Aquarium, cls.TR = create_app(), db, Aquarium, TargetRange
        cls.app.config['TESTING'] = True
        with cls.app.app_context():
            live = db.session.execute(db.text('select current_database()')).scalar()
        prod = (os.environ.get('DATABASE_URL') or '').rsplit('/', 1)[-1]
        if not live.startswith('ws_') or live == prod:
            raise RuntimeError(f'refusing to run: connected to {live!r}, not a ws_* throwaway database')
        cls.c = cls.app.test_client()

    def setUp(self):
        r = self.c.post('/create-aquarium', json={'name': 'test-tank-t', 'code': 'TT1'})
        self.tid = r.get_json()['id']

    def tearDown(self):
        with self.app.app_context():
            # ORM delete so readings/targets cascade (a bulk delete would hit the readings FK)
            for a in self.Aquarium.query.filter(self.Aquarium.name.like('test-tank-%')):
                self.db.session.delete(a)
            self.db.session.commit()

    def put(self, targets):
        return self.c.post(f'/aquarium/{self.tid}/targets', json={'targets': targets})

    def rows(self):
        with self.app.app_context():
            return {t.parameter: (t.min, t.max) for t in self.TR.query.filter_by(aquarium_id=self.tid)}

    def test_create_update_delete(self):
        self.assertTrue(self.put({'nitrate': {'min': 10, 'max': 20}, 'co2_drop': {'min': '0.9', 'max': '1.1'}}).get_json()['success'])
        self.assertEqual(self.rows(), {'nitrate': (10, 20), 'co2_drop': (0.9, 1.1)})
        self.put({'nitrate': {'min': 5, 'max': None}})                  # open top; co2_drop untouched
        self.assertEqual(self.rows(), {'nitrate': (5, None), 'co2_drop': (0.9, 1.1)})
        self.put({'nitrate': {'min': '', 'max': ''}})                   # both blank removes
        self.assertEqual(self.rows(), {'co2_drop': (0.9, 1.1)})

    def test_form_post(self):
        r = self.c.post(f'/aquarium/{self.tid}/targets', data={'min_ec': '280', 'max_ec': '320', 'min_kh': '', 'max_kh': ''})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.rows(), {'ec': (280, 320)})

    def test_validation_is_all_or_nothing(self):
        cases = [
            ({'nitrate': {'min': 20, 'max': 10}}, 'min is above max'),
            ({'nitrate': {'min': 'lots'}}, 'not a number'),
            ({'ec': {'max': 5000}}, 'plausible range'),
            ({'ec': {'min': 'nan'}}, 'plausible range'),
            ({'co2_drop': {'max': 4}}, 'plausible range'),
            ({'nonesuch': {'min': 1}}, 'unknown parameter'),
        ]
        for targets, msg in cases:
            with self.subTest(targets=targets):
                r = self.put({'kh': {'min': 3, 'max': 5}, **targets})
                self.assertEqual(r.status_code, 400)
                self.assertIn(msg, r.get_json()['error'])
                self.assertEqual(self.rows(), {})       # the valid kh entry was not written either
        self.assertEqual(self.c.post(f'/aquarium/{self.tid}/targets', json={'targets': [1]}).status_code, 400)

    def test_db_constraints_back_the_validation(self):
        from sqlalchemy.exc import IntegrityError
        with self.app.app_context():
            for lo, hi in ((5, 1), (None, None)):
                self.db.session.add(self.TR(aquarium_id=self.tid, parameter='ec', min=lo, max=hi))
                with self.assertRaises(IntegrityError):
                    self.db.session.commit()
                self.db.session.rollback()

    def test_deleting_tank_removes_targets(self):
        self.put({'ec': {'min': 1, 'max': 2}})
        self.c.post(f'/aquarium/{self.tid}/delete', json={})
        with self.app.app_context():
            self.assertEqual(self.TR.query.filter_by(aquarium_id=self.tid).count(), 0)

    def test_new_tank_goes_last_and_order_is_editable(self):
        with self.app.app_context():
            orders = [a.sort_order for a in self.Aquarium.query.all()]
            self.assertEqual(self.db.session.get(self.Aquarium, self.tid).sort_order, max(orders))
        self.c.post(f'/aquarium/{self.tid}/edit', json={'sort_order': '-1'})
        page = self.c.get('/').get_data(as_text=True)
        self.assertLess(page.index('>TT1</a>'), page.index('>100P</a>') if '>100P</a>' in page else len(page))
        self.assertEqual(self.c.post(f'/aquarium/{self.tid}/edit', json={'sort_order': '1.5'}).status_code, 400)

    def test_last_tank_remembered(self):
        r = self.c.get(f'/?aquarium_id={self.tid}')
        self.assertIn(f'ws_tank={self.tid}', r.headers.get('Set-Cookie', ''))
        page = self.c.get('/').get_data(as_text=True)          # test client keeps the cookie
        self.assertIn('aria-current="page">TT1</a>', page.replace('\n', '').replace('  ', ''))

    def test_co2_window_edit(self):
        edit = lambda **d: self.c.post(f'/aquarium/{self.tid}/edit', json=d)
        self.assertTrue(edit(co2_on='04:45', co2_off='13:45').get_json()['success'])
        with self.app.app_context():
            a = self.db.session.get(self.Aquarium, self.tid)
            self.assertEqual((str(a.co2_on), str(a.co2_off)), ('04:45:00', '13:45:00'))
        for bad, msg in (({'co2_on': '05:00', 'co2_off': ''}, 'both'), ({'co2_on': '5pm', 'co2_off': '06:00'}, 'HH:MM'),
                         ({'co2_on': '06:00', 'co2_off': '06:00'}, 'same')):
            with self.subTest(bad=bad):
                r = edit(**bad)
                self.assertEqual(r.status_code, 400)
                self.assertIn(msg, r.get_json()['error'])
        edit(co2_on='', co2_off='')                     # clearing both removes the window
        with self.app.app_context():
            self.assertIsNone(self.db.session.get(self.Aquarium, self.tid).co2_on)

    def test_series_endpoint(self):
        self.c.post(f'/api/aquarium/{self.tid}/readings', json={'readings': [{'parameter': 'ec', 'value': 300}]})
        out = self.c.get(f'/api/aquarium/{self.tid}/series?key=ec').get_json()
        self.assertEqual([p['y'] for p in out['points']], [300])
        self.assertEqual(self.c.get(f'/api/aquarium/{self.tid}/series?key=co2_drop').get_json()['points'], [])
        self.assertEqual(self.c.get(f'/api/aquarium/{self.tid}/series?key=nope').status_code, 400)
        self.assertEqual(self.c.get('/api/aquarium/999999/series?key=ec').status_code, 404)

    def test_log_endpoint(self):
        self.c.post(f'/api/aquarium/{self.tid}/readings', json={'date': '2026-11-06', 'time': '06:00', 'readings': [
            {'parameter': 'ec', 'value': 300, 'notes': 'pre'}, {'parameter': 'kh', 'value': 4, 'notes': 'pre'}]})
        self.c.post(f'/api/aquarium/{self.tid}/events', json={'date': '2026-11-06', 'time': '10:00', 'event_type': 'water_change', 'value': 50})
        days = self.c.get(f'/api/aquarium/{self.tid}/log').get_json()['days']
        self.assertEqual([(i['kind'], i['time']) for i in days[0]['items']], [('session', '06:00'), ('event', '10:00')])
        self.assertEqual(days[0]['items'][0]['shared_note'], 'pre')
        self.assertEqual(self.c.get('/api/aquarium/999999/log').status_code, 404)


if __name__ == '__main__':
    unittest.main()
