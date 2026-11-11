"""Every tank needs a code. Needs a throwaway DB (never prod):
WATERSCRIBE_TEST_DATABASE_URL=postgresql://.../ws_rh_ok venv/bin/python -m unittest tests.test_tank_code -v"""
import os
import unittest

URL = os.environ.get('WATERSCRIBE_TEST_DATABASE_URL')


@unittest.skipUnless(URL, 'set WATERSCRIBE_TEST_DATABASE_URL to a throwaway database')
class TankCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # app.config reads DATABASE_URL once, at import, and another test module may already have
        # imported it with prod's .env loaded. So set the URI on the config class, then check the
        # live connection before anything writes.
        from app.config import config
        config['default'].SQLALCHEMY_DATABASE_URI = URL
        from app import create_app, db
        from app.models import Aquarium
        cls.app, cls.db, cls.Aquarium = create_app(), db, Aquarium
        cls.app.config['TESTING'] = True
        with cls.app.app_context():
            live = db.session.execute(db.text('select current_database()')).scalar()
        prod = (os.environ.get('DATABASE_URL') or '').rsplit('/', 1)[-1]
        if not live.startswith('ws_') or live == prod:
            raise RuntimeError(f'refusing to run: connected to {live!r}, not a ws_* throwaway database')
        cls.c = cls.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            self.Aquarium.query.filter(self.Aquarium.name.like('test-tank-%')).delete()
            self.db.session.commit()

    def create(self, **data):
        return self.c.post('/create-aquarium', json={'name': 'test-tank-1', **data})

    def test_create_without_code_rejected(self):
        for data in ({}, {'code': ''}, {'code': '   '}, {'code': None}):
            with self.subTest(data=data):
                r = self.create(**data)
                self.assertEqual(r.status_code, 400)
                self.assertIn('Code is required', r.get_json()['error'])

    def test_create_with_bad_or_taken_code_rejected(self):
        self.assertIn('1-10 letters', self.create(code='has space').get_json()['error'])
        self.assertIn('already used', self.create(code='100p').get_json()['error'])

    def test_create_with_code_uppercases_it(self):
        r = self.create(code='tt9')
        self.assertTrue(r.get_json()['success'])
        with self.app.app_context():
            self.assertEqual(self.Aquarium.query.filter_by(name='test-tank-1').one().code, 'TT9')

    def test_edit_cannot_blank_the_code(self):
        tid = self.create(code='TT8').get_json()['id']
        r = self.c.post(f'/aquarium/{tid}/edit', json={'code': ''})
        self.assertEqual(r.status_code, 400)
        r = self.c.post(f'/aquarium/{tid}/edit', json={'name': 'test-tank-2'})   # code absent: unchanged
        with self.app.app_context():
            self.assertEqual(self.db.session.get(self.Aquarium, tid).code, 'TT8')

    def test_database_refuses_codeless_tank(self):
        from sqlalchemy.exc import IntegrityError
        with self.app.app_context():
            self.db.session.add(self.Aquarium(name='test-tank-3'))
            with self.assertRaises(IntegrityError):
                self.db.session.commit()
            self.db.session.rollback()

    def test_forms_require_code_and_quick_add_goes_to_manage(self):
        page = self.c.get('/aquariums').get_data(as_text=True)
        self.assertIn('id="code-new" name="code" maxlength="10" placeholder="e.g. 100P" required', page)
        tid = self.create(code='TT7').get_json()['id']
        dash = self.c.get(f'/?aquarium_id={tid}').get_data(as_text=True)
        self.assertIn("window.location.href = '/aquariums#add'", dash)
        self.assertNotIn("prompt('Enter aquarium name:')", dash)


if __name__ == '__main__':
    unittest.main()
