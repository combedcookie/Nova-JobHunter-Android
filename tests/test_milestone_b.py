#!/usr/bin/env python3
"""Milestone B tests: sources, filters, rate limits, metadata, dashboard.

No network: API responses are fake (synthetic) dicts passed in via `fetch`.
Run:  python -m unittest discover -s tests -v
"""
import io, json, os, shutil, sqlite3, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import nova_sources as ns  # noqa: E402
import job_hunter as jh   # noqa: E402
from test_milestone_a import profile  # noqa: E402

GH = {'jobs': [
    {'id': 101, 'title': 'IT Support Specialist', 'absolute_url': 'https://job-boards.greenhouse.io/acme/jobs/101',
     'location': {'name': 'Columbus, OH'}, 'first_published': '2026-10-01T09:00:00-04:00',
     'content': '&lt;p&gt;Remote-friendly.&lt;/p&gt;&lt;h3&gt;Requirements:&lt;/h3&gt;&lt;ul&gt;'
                '&lt;li&gt;Troubleshooting Windows and Linux&lt;/li&gt;&lt;li&gt;CompTIA A+ required&lt;/li&gt;&lt;/ul&gt;'
                '&lt;p&gt;$50,000 — $62,000 USD&lt;/p&gt;'},
    {'id': 102, 'title': 'Senior Staff Support Engineer', 'absolute_url': 'https://x/102',
     'location': {'name': 'Remote, US'}, 'content': 'Linux.'},
    {'id': 103, 'title': 'Help Desk Technician', 'absolute_url': 'https://x/103',
     'location': {'name': 'Remote, France'}, 'content': 'Troubleshooting.'},
    {'id': 104, 'title': 'Account Executive', 'absolute_url': 'https://x/104',
     'location': {'name': 'Remote'}, 'content': 'Sales.'},
]}
LEVER = [{
    'id': 'abc-1', 'text': 'QA Tester', 'hostedUrl': 'https://jobs.lever.co/beta/abc-1', 'createdAt': 1790000000000,
    'categories': {'location': 'Remote'}, 'workplaceType': 'remote',
    'descriptionPlain': 'Test our Android app.',
    'lists': [{'text': 'Requirements', 'content': '<li>Python testing</li><li>Must be authorized to work in the US</li>'},
              {'text': 'Nice to have', 'content': '<li>Kotlin</li>'}],
    'additionalPlain': '', 'salaryRange': {'min': 24, 'max': 30, 'currency': 'USD', 'interval': 'per-hour-wage'}}]


def fake_fetch(responses, calls=None):
    def fetch(url, timeout):
        if calls is not None:
            calls.append(url)
        for key, val in responses.items():
            if key in url:
                if isinstance(val, Exception):
                    raise val
                return val
        raise ns.SourceError('HTTP 404')
    return fetch


class Adapters(unittest.TestCase):
    def test_b01_greenhouse_parse_and_html(self):
        rows = ns.read_greenhouse({'board': 'acme', 'company': 'Acme'}, fake_fetch({'acme': GH}), 5)
        r = rows[0]
        self.assertEqual((r['title'], r['company'], r['location'], r['external_id']),
                         ('IT Support Specialist', 'Acme', 'Columbus, OH', '101'))
        self.assertIn('Requirements:', r['description'])
        self.assertIn('- CompTIA A+ required', r['description'])
        self.assertNotIn('&lt;', r['description'])
        self.assertNotIn('<', r['description'])

    def test_b02_lever_lists_salary_workplace(self):
        r = ns.read_lever({'board': 'beta', 'company': 'Beta'}, fake_fetch({'beta': LEVER}), 5)[0]
        self.assertEqual((r['pay_min'], r['pay_max'], r['pay_period']), ('24', '30', 'hour'))
        self.assertIn('Requirements:', r['description'])
        self.assertIn('Nice to have:', r['description'])
        self.assertTrue(r['posted_at'].startswith('2026'))

    def test_b03_filters(self):
        P = profile(commute_ok_cities=['Columbus', 'Newark'])
        f = {'title_any': 'profile', 'location_any': 'profile'}
        res = {j['title']: ns.passes_filter({'title': j['title'], 'location': j['location']['name']}, f, P) for j in GH['jobs']}
        self.assertEqual(res, {'IT Support Specialist': None, 'Senior Staff Support Engineer': 'seniority',
                               'Help Desk Technician': 'location', 'Account Executive': 'title'})
        self.assertIsNone(ns.passes_filter({'title': 'Help Desk', 'location': 'Remote'}, f, P))
        self.assertIsNone(ns.passes_filter({'title': 'Anything', 'location': 'Mars'}, None, P))  # local default: no filter

    def test_b04_config_validation(self):
        d = Path(tempfile.mkdtemp())
        (d / 's.json').write_text(json.dumps({'sources': [{'name': 'a', 'type': 'csv', 'path': 'x'},
                                                          {'name': 'a', 'type': 'csv', 'path': 'y'}]}))
        with self.assertRaises(ns.SourceError):
            ns.load_config(d / 's.json')
        (d / 's.json').write_text(json.dumps({'sources': [{'name': 'li', 'type': 'linkedin'}]}))
        with self.assertRaises(ns.SourceError):
            ns.load_config(d / 's.json')
        shutil.rmtree(d)

    def test_b05_bare_salary_range_only_when_annual_sized(self):
        import nova_rank
        p = nova_rank.extract_pay_text('United States Salary Range\n$86,500 — $146,400 USD')
        self.assertEqual((p['pay_min'], p['pay_period'], p['pay_source']), (86500, 'year', 'listing_text_period_assumed'))
        self.assertIsNone(nova_rank.extract_pay_text('Earn $20 - $25 depending on experience'))


class Run(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='jh_b_'))
        os.environ['JOBHUNTER_HOME'] = str(self.dir)
        os.environ.pop('JOBHUNTER_EMAIL_IMPORT', None)
        (self.dir / 'profile.json').write_text(json.dumps(profile(commute_ok_cities=['Columbus'])), encoding='utf-8')
        (self.dir / 'local.csv').write_text(
            'title,company,url,description\n'
            'IT Support Specialist,Acme,https://job-boards.greenhouse.io/acme/jobs/101?utm_source=x,"dup of greenhouse 101"\n'
            'Help Desk,LocalCo,,"Onsite Newark, OH. Troubleshooting."\n', encoding='utf-8')
        self.cfg([{'name': 'local', 'type': 'csv', 'path': 'local.csv'},
                  {'name': 'acme', 'type': 'greenhouse', 'board': 'acme', 'company': 'Acme'},
                  {'name': 'beta', 'type': 'lever', 'board': 'beta', 'company': 'Beta'},
                  {'name': 'off', 'type': 'lever', 'board': 'nope', 'enabled': False}])

    def tearDown(self):
        os.environ.pop('JOBHUNTER_HOME', None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def cfg(self, sources, **defaults):
        (self.dir / 'sources.json').write_text(json.dumps({'defaults': {'request_delay_seconds': 0, **defaults},
                                                           'sources': sources}), encoding='utf-8')

    def run_(self, fetch, **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            res = jh.run(fetch=fetch, sleep=kw.pop('sleep', lambda s: None), **kw)
        return res, buf.getvalue()

    def db(self, sql, *a):
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        try:
            rows = con.execute(sql, a).fetchall()
            con.commit()
            return rows
        finally:
            con.close()

    def test_b06_run_ingests_metadata_and_cross_source_dedup(self):
        calls = []
        (results, new), out = self.run_(fake_fetch({'acme': GH, 'beta': LEVER}, calls))
        st = {r[0]: r for r in results}
        self.assertEqual(st['local'][1:3], ('ok', 2))
        self.assertEqual(st['acme'][1:5], ('ok', 0, 1, 3))   # 101 dup of the CSV row; 3 filtered
        self.assertEqual(st['beta'][1:3], ('ok', 1))
        self.assertEqual(st['off'][1], 'disabled')
        self.assertFalse(any('nope' in c for c in calls))   # disabled source never fetched
        row = self.db("SELECT source,source_type,external_id,source_location,posted_at,first_seen_at,last_seen_at,pay_source "
                      "FROM jobs WHERE title='QA Tester'")[0]
        self.assertEqual(row[:4], ('beta', 'lever', 'abc-1', 'Remote'))
        self.assertTrue(row[4] and row[5] and row[6])
        self.assertEqual(row[7], 'listing_fields')
        self.assertIn('Discovered', out)
        src = self.db('SELECT name,last_status,last_new,last_dup,last_filtered FROM sources ORDER BY name')
        self.assertIn(('acme', 'ok', 0, 1, 3), src)

    def test_b07_rate_limit_and_force_floor(self):
        calls = []
        f = fake_fetch({'acme': GH, 'beta': LEVER}, calls)
        self.run_(f)
        n = len(calls)
        (results, _), _ = self.run_(f)
        self.assertEqual(len(calls), n)                       # network sources skipped
        st = {r[0]: r[1] for r in results}
        self.assertTrue(st['acme'].startswith('wait'))
        self.assertEqual(st['local'], 'ok')                   # local files always re-read
        (results, _), _ = self.run_(f, force=True)
        self.assertEqual(len(calls), n)                       # --force still respects 10-minute floor
        self.db("UPDATE sources SET last_checked_at='2000-01-01T00:00:00+00:00'")
        self.run_(f, force=True)
        self.assertEqual(len(calls), n + 2)

    def test_b08_error_isolated_and_last_ok_preserved(self):
        self.run_(fake_fetch({'acme': GH, 'beta': LEVER}))
        self.db("UPDATE sources SET last_checked_at='2000-01-01T00:00:00+00:00'")
        (results, _), _ = self.run_(fake_fetch({'acme': ns.SourceError('HTTP 503'), 'beta': LEVER}))
        st = {r[0]: r[1] for r in results}
        self.assertEqual(st['acme'], 'error: HTTP 503')
        self.assertEqual(st['beta'], 'ok')
        last_ok = self.db("SELECT last_ok_at FROM sources WHERE name='acme'")[0][0]
        self.assertIsNotNone(last_ok)

    def test_b09_delay_between_network_sources(self):
        self.cfg([{'name': 'acme', 'type': 'greenhouse', 'board': 'acme'},
                  {'name': 'beta', 'type': 'lever', 'board': 'beta'}], request_delay_seconds=3)
        slept = []
        self.run_(fake_fetch({'acme': GH, 'beta': LEVER}), sleep=slept.append)
        self.assertEqual(slept, [3.0])                        # one delay between two network calls

    def test_b10_json_source_formats_and_bad_file(self):
        (self.dir / 'a.json').write_text(json.dumps([{'title': 'QA Tester', 'company': 'J1', 'description': 'Python testing.'}]))
        (self.dir / 'b.json').write_text(json.dumps({'jobs': [{'title': 'Help Desk', 'company': 'J2', 'description': 'Remote.', 'pay_min': None}]}))
        (self.dir / 'c.json').write_text('{not json')
        self.cfg([{'name': 'a', 'type': 'json', 'path': 'a.json'}, {'name': 'b', 'type': 'json', 'path': 'b.json'},
                  {'name': 'c', 'type': 'json', 'path': 'c.json'}, {'name': 'd', 'type': 'csv', 'path': 'missing.csv'}])
        (results, _), _ = self.run_(fake_fetch({}))
        st = {r[0]: r for r in results}
        self.assertEqual(st['a'][1:3], ('ok', 1))
        self.assertEqual(st['b'][1:3], ('ok', 1))
        self.assertTrue(st['c'][1].startswith('error'))
        self.assertTrue(st['d'][1].startswith('error: file not found'))

    def test_b11_dashboard_counts(self):
        self.run_(fake_fetch({'acme': GH, 'beta': LEVER}))
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        con.execute("UPDATE jobs SET gate='pass',final_score=80,traditional_score=80,exploration_score=50,status='discovered' WHERE id=1")
        con.execute("UPDATE jobs SET gate='review',final_score=50,traditional_score=30,exploration_score=70,status='prepared' WHERE id=2")
        con.execute("UPDATE jobs SET status='submitted' WHERE id=3")
        con.commit()
        c = jh.counts(con, 60, 60)
        con.close()
        self.assertEqual((c['discovered'], c['high'], c['unconv'], c['prepared'], c['submitted']), (3, 1, 1, 1, 1))

    def test_b12_rescore_keeps_source_location(self):
        self.run_(fake_fetch({'acme': GH, 'beta': LEVER}))
        before = self.db("SELECT location FROM jobs WHERE title='QA Tester'")[0][0]
        with redirect_stdout(io.StringIO()):
            jh.rescore()
        self.assertEqual(self.db("SELECT location FROM jobs WHERE title='QA Tester'")[0][0], before)
        self.assertEqual(before, 'Remote')


if __name__ == '__main__':
    unittest.main(verbosity=2)
