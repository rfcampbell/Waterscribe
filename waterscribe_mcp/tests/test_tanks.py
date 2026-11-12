"""list_tanks flags code-less tanks; tools refuse them."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # find testenv however the tests are run
import testenv   # first: temp state dir, dead API
server = testenv.import_server()
from mcp.server.mcpserver.exceptions import ToolError

TANKS = [{'id': 4, 'code': '100P', 'name': '100p'}, {'id': 9, 'code': None, 'name': 'Hastatus QT', 'volume_gallons': 10.0}]


class Tanks(unittest.TestCase):
    def setUp(self):
        self.calls = []
        async def fake_api(method, path, **kw):
            self.calls.append((method, path))
            if path == '/aquariums':
                return TANKS
            raise AssertionError(f'unexpected call {method} {path}')
        self.orig, server.api = server.api, fake_api

    def tearDown(self):
        server.api = self.orig

    def test_list_tanks_skips_and_flags_codeless(self):
        out = asyncio.run(server.list_tanks.__wrapped__())
        self.assertEqual([t['code'] for t in out['tanks']], ['100P'])
        self.assertEqual(out['without_code'], ['Hastatus QT'])
        self.assertIn('warning', out)

    def test_list_tanks_has_no_warning_when_all_coded(self):
        server_tanks, TANKS[1]['code'] = TANKS[1]['code'], 'HQT'
        try:
            out = asyncio.run(server.list_tanks.__wrapped__())
            self.assertNotIn('without_code', out)
        finally:
            TANKS[1]['code'] = server_tanks

    def test_codeless_tank_refused_by_name_or_id_and_nothing_written(self):
        for ref in ('Hastatus QT', '9'):
            with self.subTest(ref=ref), self.assertRaisesRegex(ToolError, 'has no code'):
                asyncio.run(server.resolve_tank(ref))
        self.assertEqual({p for _, p in self.calls}, {'/aquariums'})

    def test_unknown_tank_lists_only_coded(self):
        with self.assertRaises(ToolError) as cm:
            asyncio.run(server.resolve_tank('nope'))
        self.assertIn('100P (100p)', str(cm.exception))
        self.assertNotIn('Hastatus', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
