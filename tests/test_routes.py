"""Old /aquarium/<id> URL redirects to the dashboard. Needs a throwaway DB (never prod):
WATERSCRIBE_TEST_DATABASE_URL=postgresql://.../ws_x venv/bin/python -m unittest tests.test_routes -v"""
import os
import unittest

URL = os.environ.get('WATERSCRIBE_TEST_DATABASE_URL')


@unittest.skipUnless(URL, 'set WATERSCRIBE_TEST_DATABASE_URL to a throwaway database')
class AquariumDetailRedirect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.config import config
        config['default'].SQLALCHEMY_DATABASE_URI = URL
        from app import create_app, db
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        with cls.app.app_context():
            live = db.session.execute(db.text('select current_database()')).scalar()
            prod = (os.environ.get('DATABASE_URL') or '').rsplit('/', 1)[-1]
            if not live.startswith('ws_') or live == prod:
                raise RuntimeError(f'refusing to run: connected to {live!r}, not a ws_* throwaway database')
            cls.ids = [r[0] for r in db.session.execute(db.text('select id from aquariums order by id'))]
        cls.c = cls.app.test_client()

    def test_known_tank_redirects_to_dashboard(self):
        tank = self.ids[-1]
        r = self.c.get(f'/aquarium/{tank}')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers['Location'], f'/?aquarium_id={tank}')
        page = self.c.get(r.headers['Location'])
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'data-aquarium-id="{tank}"', page.get_data(as_text=True))

    def test_unknown_tank_is_404(self):
        r = self.c.get(f'/aquarium/{max(self.ids) + 1000}')
        self.assertEqual(r.status_code, 404)


if __name__ == '__main__':
    unittest.main()
