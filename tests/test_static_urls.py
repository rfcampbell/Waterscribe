"""Every /static URL carries a content version. No DB: venv/bin/python -m unittest tests.test_static_urls -v"""
import json
import os
import re
import tempfile
from pathlib import Path
import unittest
from urllib.parse import urlparse, parse_qs

from app import create_app, static_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class StaticUrls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()

    def test_no_hand_written_static_links(self):
        # templates, the manifest source and our JS must go through url_for('static')
        hits = []
        for base in ('app/templates', 'app/static/js'):
            for d, _, files in os.walk(os.path.join(ROOT, base)):
                for f in files:
                    text = Path(d, f).read_text(encoding='utf-8')
                    hits += [f'{f}: {m}' for m in re.findall(r'["\'(]/static/[^"\')\s]*', text)]
        manifest = Path(ROOT, 'app', 'manifest.json').read_text()
        hits += [f'manifest.json: {m}' for m in re.findall(r'/static/\S*', manifest)]
        self.assertEqual(hits, [])

    def test_url_for_static_is_versioned_by_content(self):
        with self.app.test_request_context():
            from flask import url_for
            for f in ('js/mainchart.js', 'favicon.ico', 'sw.js', 'icons/icon-192.png'):
                with self.subTest(f):
                    u = urlparse(url_for('static', filename=f))
                    v = parse_qs(u.query).get('v', [''])[0]
                    self.assertRegex(v, r'^[0-9a-f]{10}$')
                    self.assertEqual(v, static_hash(self.app.static_folder, f))

    def test_hash_follows_content_not_time(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.js')
            Path(p).write_text('one')
            h1 = static_hash(d, 'a.js')
            os.utime(p, (1, 1))                      # touch only: same content, same version
            self.assertEqual(static_hash(d, 'a.js'), h1)
            Path(p).write_text('two')
            self.assertNotEqual(static_hash(d, 'a.js'), h1)
            self.assertEqual(static_hash(d, 'missing.js'), '0')

    def test_manifest_icons_versioned(self):
        r = self.app.test_client().get('/manifest.webmanifest')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, 'application/manifest+json')
        self.assertIn('no-cache', r.headers['Cache-Control'])
        icons = json.loads(r.get_data())['icons']
        self.assertTrue(icons)
        for i in icons:
            self.assertRegex(i['src'], r'^/static/icons/icon-\d+\.png\?v=[0-9a-f]{10}$')


if __name__ == '__main__':
    unittest.main()
