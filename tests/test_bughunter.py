#!/usr/bin/env python3
"""BugHunter tests. Synthetic program data only; no network; nothing contacts any target."""
import ast, io, json, os, shutil, sqlite3, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import nova_bounty as nb  # noqa: E402
import job_hunter as jh   # noqa: E402
from test_milestone_a import profile  # noqa: E402

H1 = [{'handle': 'acme_vdp', 'name': 'Acme VDP', 'url': 'https://hackerone.com/acme_vdp', 'offers_bounties': False,
       'submission_state': 'open', 'response_efficiency_percentage': 95, 'offers_swag': False,
       'targets': {'in_scope': [
           {'asset_identifier': '*.acme.test', 'asset_type': 'WILDCARD', 'eligible_for_submission': True, 'eligible_for_bounty': False},
           {'asset_identifier': 'https://api.acme.test/v2/', 'asset_type': 'URL', 'eligible_for_submission': True},
           {'asset_identifier': 'com.acme.app', 'asset_type': 'GOOGLE_PLAY_APP_ID', 'eligible_for_submission': True},
           {'asset_identifier': '*.legacy.test', 'asset_type': 'OTHER', 'eligible_for_submission': True},
           {'asset_identifier': '10.20.0.0/16', 'asset_type': 'CIDR', 'eligible_for_submission': True},
           {'asset_identifier': 'old.acme.test', 'asset_type': 'URL', 'eligible_for_submission': False}],
           'out_of_scope': [{'asset_identifier': '*.corp.acme.test', 'asset_type': 'WILDCARD'},
                            {'asset_identifier': 'pay.acme.test', 'asset_type': 'URL'}]}},
      {'handle': 'closed_co', 'name': 'Closed Co', 'url': 'https://hackerone.com/closed_co', 'offers_bounties': True,
       'submission_state': 'paused', 'targets': {'in_scope': [], 'out_of_scope': []}}]
BC = [{'name': 'Big Pay ', 'url': 'https://bugcrowd.com/engagements/bigpay', 'safe_harbor': 'full', 'max_payout': 20000,
       'allows_disclosure': True, 'targets': {'in_scope': [{'type': 'network', 'target': '203.0.113.0/24'}], 'out_of_scope': []}}]
INTI = [{'id': 'x', 'name': 'Inti', 'handle': 'inti', 'company_handle': 'c', 'url': 'https://intigriti.test/inti',
         'status': 'open', 'confidentiality_level': 'public', 'tacRequired': True, 'twoFactorRequired': True,
         'min_bounty': {'value': 0, 'currency': 'EUR'}, 'max_bounty': {'value': 0, 'currency': 'EUR'},
         'targets': {'in_scope': [{'type': 'url', 'endpoint': 'https://inti.test'}], 'out_of_scope': []}}]
YWH = [{'id': 'ywh', 'name': 'YWH', 'public': False, 'disabled': False, 'min_bounty': 50, 'max_bounty': 500,
        'targets': {'in_scope': [{'target': 'https://ywh.test', 'type': 'web-application'}], 'out_of_scope': []}}]
DIO = [{'program_name': 'Tiny Town VDP', 'policy_url': 'https://tiny.test/security', 'offers_bounty': 'no',
        'safe_harbor': 'full', 'policy_url_status': 'alive', 'contact_email': 'sec@tiny.test'},
       {'program_name': 'Dead Link', 'policy_url': 'https://dead.test', 'offers_bounty': 'no', 'policy_url_status': 'dead'}]
FEED = {'hackerone': H1, 'bugcrowd': BC, 'intigriti': INTI, 'yeswehack': YWH, 'diodb': DIO}


def fake_fetch(calls=None, fail=()):
    def f(url, timeout):
        for k, v in nb.FEEDS.items():
            if url == v:
                if calls is not None:
                    calls.append(k)
                if k in fail:
                    raise RuntimeError('HTTP 503')
                return FEED[k]
        raise AssertionError('unexpected URL ' + url)
    return f


class Normalize(unittest.TestCase):
    def test_bb01_categories_and_ineligible_dropped(self):
        p = nb.normalize('hackerone', H1)[0]
        cats = {a['identifier']: a['category'] for a in p['assets']}
        self.assertEqual(cats['*.acme.test'], 'web')
        self.assertEqual(cats['com.acme.app'], 'android')
        self.assertEqual(cats['*.legacy.test'], 'web')         # OTHER but domain-shaped
        self.assertEqual(cats['10.20.0.0/16'], 'network')
        self.assertNotIn('old.acme.test', cats)                 # eligible_for_submission False

    def test_bb02_platform_flags(self):
        i = nb.normalize('intigriti', INTI)[0]
        self.assertTrue(i['flags']['terms_acceptance_required'])
        y = nb.normalize('yeswehack', YWH)[0]
        self.assertFalse(y['public'])
        d = nb.normalize('diodb', DIO)
        self.assertEqual(len(d), 1)                             # dead policy link skipped
        self.assertTrue(d[0]['flags']['scope_in_policy_only'])


class Scoring(unittest.TestCase):
    def test_bb03_gate_never_means_authorized(self):
        P = profile()
        s = {p['key']: nb.score_program(p, P) for plat, d in FEED.items() for p in nb.normalize(plat, d)}
        self.assertEqual(s['hackerone:closed_co']['gate'], 'fail')     # paused
        self.assertEqual(s['yeswehack:ywh']['gate'], 'fail')           # private
        self.assertEqual(s['intigriti:inti']['gate'], 'review')        # terms + 2FA
        self.assertEqual(s['diodb:tiny-town-vdp']['gate'], 'review')   # scope only in policy text
        self.assertEqual(s['bugcrowd:bigpay']['gate'], 'pass')

    def test_bb04_beginner_first_and_lab_labeled(self):
        P = profile()
        vdp = nb.score_program(nb.normalize('hackerone', H1)[0], P)
        big = nb.score_program(nb.normalize('bugcrowd', BC)[0], P)
        self.assertGreater(vdp['beginner'], big['beginner'])          # VDP + wildcard beats big payout network-only
        self.assertGreater(vdp['final'], big['final'])
        txt = ' '.join(vdp['reasons'])
        self.assertIn('android: android', txt)                        # real Android work counts
        self.assertIn('(LAB ONLY)', txt)                              # web via lab skills is labeled
        self.assertTrue(any(g['category'] == 'android' and 'mas.owasp.org' in g['resources'][0][1] for g in vdp['gaps']))


class Scope(unittest.TestCase):
    A = nb.normalize('hackerone', H1)[0]['assets']

    def v(self, t):
        return nb.scope_check(self.A, t)[0]

    def test_bb05_scope_rules(self):
        self.assertEqual(self.v('shop.acme.test'), 'LISTED_IN_SCOPE')
        self.assertEqual(self.v('https://shop.acme.test/cart?x=1'), 'LISTED_IN_SCOPE')
        self.assertEqual(self.v('acme.test'), 'AMBIGUOUS')             # apex of wildcard
        self.assertEqual(self.v('vpn.corp.acme.test'), 'OUT_OF_SCOPE')  # out wins over *.acme.test
        self.assertEqual(self.v('pay.acme.test'), 'OUT_OF_SCOPE')
        self.assertEqual(self.v('https://api.acme.test/v2/users'), 'LISTED_IN_SCOPE')
        self.assertEqual(self.v('https://api.acme.test/admin'), 'LISTED_IN_SCOPE')  # still *.acme.test
        self.assertEqual(self.v('10.20.5.9'), 'LISTED_IN_SCOPE')
        self.assertEqual(self.v('10.21.0.1'), 'NOT_LISTED')
        self.assertEqual(self.v('evilacme.test'), 'NOT_LISTED')        # suffix trick
        self.assertEqual(self.v('acme.test.evil.example'), 'NOT_LISTED')

    def test_bb06_path_scoped_url(self):
        assets = [nb._asset('https://only.test/app/', 'URL', True)]
        self.assertEqual(nb.scope_check(assets, 'https://only.test/app/x')[0], 'LISTED_IN_SCOPE')
        self.assertEqual(nb.scope_check(assets, 'https://only.test/other')[0], 'NOT_LISTED')


class NoActiveCode(unittest.TestCase):
    def test_bb07_module_has_no_target_network_code(self):
        src = (HERE / 'nova_bounty.py').read_text(encoding='utf-8')
        tree = ast.parse(src)
        mods = {al.name for n in ast.walk(tree) if isinstance(n, ast.Import) for al in n.names} | \
               {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        for banned in ('socket', 'subprocess', 'http.client', 'ssl'):
            self.assertNotIn(banned, mods)
        self.assertEqual(src.count('urlopen('), 1)                    # only the listing download
        self.assertTrue(all(u.startswith('https://raw.githubusercontent.com/') for u in nb.FEEDS.values()))


class Flow(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='jh_bb_'))
        os.environ['JOBHUNTER_HOME'] = str(self.dir)
        (self.dir / 'profile.json').write_text(json.dumps(profile()), encoding='utf-8')

    def tearDown(self):
        os.environ.pop('JOBHUNTER_HOME', None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def q(self, fn, *a, **k):
        if fn is jh.bb_sync:
            k.setdefault('sleep', lambda s: None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            r = fn(*a, **k)
        return r, buf.getvalue()

    def db(self, sql, *a):
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        try:
            r = con.execute(sql, a).fetchall(); con.commit(); return r
        finally:
            con.close()

    def test_bb08_sync_idempotent_rate_limited_error_isolated(self):
        calls = []
        res, out = self.q(jh.bb_sync, fetch=fake_fetch(calls, fail=('yeswehack',)))
        st = {r[0]: r for r in res}
        self.assertEqual(st['hackerone'][1:], ('ok', 2, 2))
        self.assertTrue(st['yeswehack'][1].startswith('error'))
        self.assertIn('no target was contacted', out)
        n = self.db('SELECT COUNT(*) FROM bb_programs')[0][0]
        res, _ = self.q(jh.bb_sync, fetch=fake_fetch(calls))
        self.assertTrue(all(r[1].startswith('wait') for r in res))    # rate limited
        self.db("UPDATE sources SET last_checked_at='2000-01-01T00:00:00+00:00'")
        self.q(jh.bb_sync, fetch=fake_fetch(calls))
        self.assertEqual(self.db('SELECT COUNT(*) FROM bb_programs')[0][0], n + 1)  # ywh arrives once it stops failing
        self.assertEqual(self.db("SELECT COUNT(*) FROM bb_assets WHERE program_id=1")[0][0], 7)  # replaced, not duplicated

    def test_bb09_list_plan_scope_audit(self):
        self.q(jh.bb_sync, fetch=fake_fetch())
        rows, _ = self.q(jh.bb_list)
        names = [r[1] for r in rows]
        self.assertNotIn('Closed Co', names)                           # gate fail hidden
        self.assertEqual(names[0], 'Acme VDP')                         # beginner-first
        pid = rows[0][0]
        path, out = self.q(jh.bb_plan, pid)
        text = Path(path).read_text()
        self.assertIn('PLANNING DOCUMENT ONLY', text)
        self.assertIn('Scope verification checklist', text)
        self.assertIsNone(nb.ACTIVE_TOOL_WORDS.search(text))            # no scanner commands in plans
        v, out = self.q(jh.bb_scope, pid, 'vpn.corp.acme.test')
        self.assertEqual(v, 'OUT_OF_SCOPE')
        self.assertIn('not permission to test', out)
        ev = [r[0] for r in self.db('SELECT event FROM audit')]
        self.assertIn('BB_PLAN_WRITTEN', ev)
        self.assertIn('BB_SCOPE_CHECK', ev)
        self.assertEqual(self.db('SELECT status FROM bb_programs WHERE id=?', pid)[0][0], 'studying')

    def test_bb10_skip_and_category_filter(self):
        self.q(jh.bb_sync, fetch=fake_fetch())
        rows, _ = self.q(jh.bb_list, 'final', 'android')
        self.assertEqual([r[1] for r in rows], ['Acme VDP'])
        self.q(jh.bb_mark, rows[0][0], 'skipped')
        rows, _ = self.q(jh.bb_list, 'final', 'android')
        self.assertEqual(rows, [])
