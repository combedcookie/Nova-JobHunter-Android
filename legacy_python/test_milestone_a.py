#!/usr/bin/env python3
"""Milestone A tests. Standard library unittest only (works in Termux).

Run from the project folder:  python -m unittest discover -s tests -v
All job descriptions are SYNTHETIC.
"""
import copy, csv, io, json, os, shutil, sqlite3, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import nova_rank  # noqa: E402
import job_hunter  # noqa: E402

BASE_PROFILE = json.loads((HERE / 'defaults' / 'profile.json').read_text(encoding='utf-8'))


def profile(**facts):
    p = copy.deepcopy(BASE_PROFILE)
    p['candidate_facts'].update(facts)
    return p


def job(title, desc, company='Synthetic Co', url='', **kw):
    return dict(title=title, company=company, url=url, description=desc, **kw)


def items(result, kind=None):
    return [i for i in result['requirements']['items'] if kind is None or i['kind'] == kind]


class Extraction(unittest.TestCase):
    def test_01_required_vs_preferred(self):
        r = nova_rank.evaluate_job(job('IT Support', 'CompTIA A+ required. Network+ preferred.'), profile())
        lv = {i['key']: i['level'] for i in items(r, 'credential')}
        self.assertEqual(lv, {'comptia_a_plus': 'required', 'comptia_network_plus': 'preferred'})

    def test_02_section_headers(self):
        d = 'Requirements:\nHigh school diploma or GED\nPreferred Qualifications:\nCCNA\nITIL Foundation'
        r = nova_rank.evaluate_job(job('Service Desk Analyst', d), profile(education_highest='high_school'))
        lv = {i['key']: i['level'] for i in items(r)}
        self.assertEqual(lv['high_school'], 'required')
        self.assertEqual(lv['ccna'], 'preferred')
        self.assertEqual(lv['itil'], 'preferred')

    def test_03_years_digits_words_ranges_scope(self):
        d = ('Minimum 3-5 years of help desk experience required. '
             'Five years diesel equipment repair preferred. 2+ years of experience a plus.')
        r = nova_rank.evaluate_job(job('Field Tech', d), profile())
        ys = {i['scope']: i for i in items(r, 'years')}
        self.assertEqual(ys['it']['min_years'], 3)
        self.assertEqual(ys['it']['max_years'], 5)
        self.assertEqual(ys['mechanical']['min_years'], 5)
        self.assertEqual(ys['unclear']['min_years'], 2)

    def test_04_negation_is_not_a_requirement_or_skill(self):
        d = 'No degree required. Certification not required. This is not a cybersecurity role. Troubleshooting PCs.'
        r = nova_rank.evaluate_job(job('Desktop Support', d), profile())
        self.assertEqual(items(r, 'education') + items(r, 'credential'), [])
        claims = [e['claim'] for e in r['evidence_map']]
        self.assertNotIn('cybersecurity', claims)
        self.assertIn('troubleshooting', claims)

    def test_05_location_and_work_mode(self):
        r = nova_rank.evaluate_job(job('Help Desk', 'Hybrid role based in Columbus, OH. 3 days on-site.'), profile())
        self.assertEqual(r['requirements']['location'], 'Columbus, OH')
        self.assertEqual(set(r['requirements']['work_modes']), {'hybrid', 'onsite'})
        r1 = nova_rank.evaluate_job(job('Help Desk', 'Onsite Newark, OH. Based in Mount Vernon, OH too.'), profile())
        self.assertEqual(r1['requirements']['location'], 'Newark, OH')
        r2 = nova_rank.evaluate_job(job('Help Desk', 'Fully remote, US only.'), profile())
        self.assertEqual(r2['requirements']['work_modes'], ['remote'])
        r3 = nova_rank.evaluate_job(job('Help Desk', 'Troubleshooting.'), profile())
        self.assertTrue(any('Work mode' in u for u in r3['unknowns']))
        self.assertTrue(any('Location not stated' in u for u in r3['unknowns']))

    def test_06_salary_from_text_never_estimated(self):
        p = nova_rank.extract_pay_text('Pay: $20 - $24 per hour, plus benefits.')
        self.assertEqual((p['pay_min'], p['pay_max'], p['pay_period'], p['pay_source']), (20, 24, 'hour', 'listing_text'))
        p = nova_rank.extract_pay_text('Salary $55k-$65k/year.')
        self.assertEqual((p['pay_min'], p['pay_max'], p['pay_period']), (55000, 65000, 'year'))
        self.assertIsNone(nova_rank.extract_pay_text('Competitive pay. Great team.'))

    def test_07_work_auth_travel_shift(self):
        d = ('Must be authorized to work in the US. We are unable to sponsor visas. '
             'Travel up to 25% required. Rotating schedule including weekends and on-call.')
        r = nova_rank.evaluate_job(job('Field Service Technician', d), profile())
        keys = {i['key'] for i in items(r)}
        self.assertTrue({'work_authorized_us', 'no_sponsorship', 'travel', 'weekend', 'on_call', 'rotating'} <= keys)
        self.assertEqual(items(r, 'travel')[0]['pct'], 25)


class GateAndEvidence(unittest.TestCase):
    def test_08_required_clearance_fails_gate(self):
        r = nova_rank.evaluate_job(job('IT Support', 'Active Secret clearance required. Troubleshooting.'), profile())
        self.assertEqual(r['gate'], 'fail')
        self.assertTrue(any('clearance' in d for d in r['disqualifiers']))
        self.assertLessEqual(r['final'], 20)

    def test_09_unknown_fact_goes_to_review_not_pass_or_fail(self):
        r = nova_rank.evaluate_job(job('Help Desk', 'Remote. Must be authorized to work in the US.'),
                                   profile(work_authorized_us=None))
        self.assertEqual(r['gate'], 'review')
        self.assertTrue(any('work_authorized_us' in u for u in r['unknowns']))
        r2 = nova_rank.evaluate_job(job('Help Desk', 'Remote. Must be authorized to work in the US.'),
                                    profile(work_authorized_us=True))
        self.assertEqual(r2['gate'], 'pass')

    def test_10_or_equivalent_degree_is_review_not_fail(self):
        d = "Remote. Bachelor's degree or equivalent experience required."
        r = nova_rank.evaluate_job(job('QA Tester', d), profile(education_highest='high_school'))
        self.assertEqual(r['gate'], 'review')
        r2 = nova_rank.evaluate_job(job('QA Tester', "Remote. Bachelor's degree required."),
                                    profile(education_highest='high_school'))
        self.assertEqual(r2['gate'], 'fail')

    def test_11_preferred_never_blocks(self):
        r = nova_rank.evaluate_job(job('Help Desk', 'Remote. CCNA preferred. 5+ years IT preferred.'), profile())
        self.assertEqual(r['gate'], 'pass')
        self.assertEqual(r['disqualifiers'], [])

    def test_12_missing_evidence_never_upgraded(self):
        p = profile()
        p['evidence'] = [
            {'id': 'X1', 'type': 'portfolio', 'status': 'verified', 'ref': 'not-a-url', 'skills': ['python']},
            {'id': 'X2', 'type': 'resume', 'status': 'verified', 'ref': '', 'skills': ['linux']},
            {'id': 'X3', 'type': 'resume', 'status': 'verified', 'ref': 'resume.txt:L4', 'skills': ['testing']},
            {'id': 'X4', 'type': 'resume', 'status': 'totally_legit', 'ref': 'x', 'skills': ['android']},
        ]
        r = nova_rank.evaluate_job(job('QA Tester', 'Python, Linux, testing, Android, kotlin.'), p)
        st = {e['claim']: e for e in r['evidence_map']}
        self.assertEqual(st['python']['status'], 'self_reported')
        self.assertTrue(st['python']['downgraded'])
        self.assertEqual(st['linux']['status'], 'self_reported')
        self.assertEqual(st['testing']['status'], 'verified')
        self.assertEqual(st['android']['status'], 'self_reported')
        self.assertEqual(st['kotlin']['status'], 'self_reported')  # no evidence entry at all
        self.assertEqual(st['kotlin']['ref'], None)

    def test_13_misleading_title_and_keyword_matches(self):
        r = nova_rank.evaluate_job(job('Squad Lead, Aquarium Maintenance', 'Feed fish. Clean tanks.'), profile())
        self.assertIn('Target role title match: none', r['reasons'])
        r2 = nova_rank.evaluate_job(job('Barista', 'We love Pythons at the zoo? No. Javascript-free kotlinish shop.'), profile())
        claims = [e['claim'] for e in r2['evidence_map']]
        self.assertNotIn('kotlin', claims)
        self.assertLess(r2['conventional'], 30)

    def test_14_learning_counts_less_than_demonstrated(self):
        a = nova_rank.evaluate_job(job('Analyst', 'Python, Linux, troubleshooting.'), profile())
        b = nova_rank.evaluate_job(job('Analyst', 'Networking, DNS, VPN.'), profile())
        self.assertGreater(a['conventional'], b['conventional'])
        self.assertTrue(all(e.get('note') for e in b['evidence_map'] if e['kind'] == 'learning_lab'))


class Preferences(unittest.TestCase):
    def test_20_shift_no_fails_unknown_reviews_day_passes(self):
        P = profile(shifts_ok=['day'], shifts_no=['evening'], work_authorized_us=True)
        self.assertEqual(nova_rank.evaluate_job(job('Help Desk', 'Remote. Second shift required.'), P)['gate'], 'fail')
        self.assertEqual(nova_rank.evaluate_job(job('Help Desk', 'Remote. Weekends required.'), P)['gate'], 'review')
        self.assertEqual(nova_rank.evaluate_job(job('Help Desk', 'Remote. 1st shift, Monday-Friday.'), P)['gate'], 'pass')

    def test_21_commute_list_silences_note_only_for_listed_cities(self):
        P = profile(location='Newark, OH', commute_ok_cities=['Columbus'], max_commute_minutes=60)
        r = nova_rank.evaluate_job(job('Help Desk', 'Onsite in Columbus, OH.'), P)
        self.assertFalse(any('commute' in u for u in r['unknowns']))
        r = nova_rank.evaluate_job(job('Help Desk', 'Onsite in Dayton, OH.'), P)
        self.assertTrue(any('max 60 min' in u for u in r['unknowns']))
        self.assertNotEqual(r['gate'], 'fail')  # commute is a note, never an auto-fail


class CLI(unittest.TestCase):
    """Uses a temporary JOBHUNTER_HOME so your real database is never touched."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='jh_test_'))
        os.environ['JOBHUNTER_HOME'] = str(self.dir)
        for k in ('JOBHUNTER_EMAIL_TO', 'JOBHUNTER_EMAIL_FROM', 'JOBHUNTER_SMTP_PASSWORD', 'JOBHUNTER_EMAIL_IMPORT'):
            os.environ.pop(k, None)
        # Fixed test facts so editing your real profile.json never breaks these tests.
        (self.dir / 'profile.json').write_text(json.dumps(profile(work_authorized_us=None, us_citizen=None)), encoding='utf-8')

    def tearDown(self):
        os.environ.pop('JOBHUNTER_HOME', None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def csv(self, rows, name='jobs.csv'):
        path = self.dir / name
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['title', 'company', 'url', 'description', 'pay_min', 'pay_max', 'pay_period', 'pay_currency'])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return path

    def quiet(self, fn, *a):
        buf = io.StringIO()
        with redirect_stdout(buf):
            out = fn(*a)
        return out, buf.getvalue()

    def test_15_duplicates_tracking_params_whitespace_and_reposts(self):
        d = 'Remote help desk. Troubleshooting.'
        p = self.csv([
            dict(title='Help Desk Tech', company='Acme', url='https://www.acme.com/jobs/1/', description=d),
            dict(title=' help desk  tech ', company='ACME', url='https://acme.com/jobs/1?utm_source=x&ref=y', description=d),
            dict(title='Help Desk Tech', company='Acme', url='https://boards.example/acme-42', description=d + ' '),
            dict(title='Help Desk Tech', company='Acme', url='https://acme.com/jobs/2', description='Different onsite role.'),
        ])
        (new, dup, bad), _ = self.quiet(job_hunter.import_csv, str(p))
        self.assertEqual((new, dup, bad), (2, 2, 0))
        (new, dup, bad), _ = self.quiet(job_hunter.import_csv, str(p))
        self.assertEqual((new, dup), (0, 4))

    def test_16_import_sets_needs_review_and_pay_source(self):
        p = self.csv([
            dict(title='IT Support', company='A', description='Remote. Must be authorized to work in the US. $20-$24/hour.'),
            dict(title='IT Support', company='B', description='Remote troubleshooting.', pay_min='50000', pay_max='60000', pay_period='year'),
            dict(title='IT Support', company='C', description='Remote troubleshooting. Competitive pay.'),
            dict(title='IT Support', company='D', description='Bad pay row', pay_min='abc', pay_period='hour'),
        ])
        (new, dup, bad), _ = self.quiet(job_hunter.import_csv, str(p))
        self.assertEqual((new, bad), (3, 1))
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        rows = {r[0]: r[1:] for r in con.execute('SELECT company,status,gate,pay_source,pay_min,pay_currency FROM jobs')}
        con.close()
        self.assertEqual(rows['A'][:3], ('needs_review', 'review', 'listing_text'))
        self.assertEqual(rows['A'][3], 20)
        self.assertEqual(rows['B'][2], 'listing_fields')
        self.assertEqual(rows['C'][2:], (None, None, None))  # undisclosed stays undisclosed

    def test_17_whitespace_confirmation_rejected_and_gate_override(self):
        p = self.csv([dict(title='IT Support', company='A', description='Remote troubleshooting.'),
                      dict(title='IT Support', company='B', description='Remote. Secret clearance required.')])
        self.quiet(job_hunter.import_csv, str(p))
        self.quiet(job_hunter.change_status, 1, 'shortlisted')
        self.quiet(job_hunter.prepare, 1)
        self.quiet(job_hunter.approve, 1, 'reviewed')
        with self.assertRaises(SystemExit):
            self.quiet(job_hunter.change_status, 1, 'submitted', '   ')
        self.quiet(job_hunter.change_status, 1, 'submitted', 'CONF-12345')
        with self.assertRaises(SystemExit):
            self.quiet(job_hunter.change_status, 2, 'shortlisted')
        self.quiet(job_hunter.change_status, 2, 'shortlisted', '', 'Recruiter said clearance sponsored')
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        self.assertEqual(con.execute('SELECT status,gate_override FROM jobs WHERE id=2').fetchone(),
                         ('shortlisted', 'Recruiter said clearance sponsored'))
        n_audit = con.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
        con.close()
        n_jsonl = len((self.dir / 'notifications.jsonl').read_text().splitlines())
        self.assertEqual(n_audit, n_jsonl)  # JSONL only written for committed events

    def test_18_migrates_v01_database_and_rescore(self):
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        con.executescript('''CREATE TABLE jobs (id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
            company TEXT NOT NULL, url TEXT, description TEXT NOT NULL, traditional_score INTEGER NOT NULL,
            exploration_score INTEGER NOT NULL, evidence_score INTEGER NOT NULL, final_score INTEGER NOT NULL,
            reasons TEXT NOT NULL, gaps TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'discovered',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);''')
        old = dict(title='Help Desk', company='Old Co', url='https://old.co/1', description='CISSP required.')
        con.execute("INSERT INTO jobs VALUES (1,?,?,?,?,?,50,50,100,50,'[]','[]','shortlisted','t','t')",
                    (job_hunter.legacy_fingerprint(old), old['title'], old['company'], old['url'], old['description']))
        con.commit(); con.close()
        self.quiet(job_hunter.rescore)
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        row = con.execute('SELECT status,gate,pay_min FROM jobs WHERE id=1').fetchone()
        con.close()
        self.assertEqual(row, ('shortlisted', 'fail', None))  # rescore never changes status
        p = self.csv([old])
        (new, dup, _), _ = self.quiet(job_hunter.import_csv, str(p))
        self.assertEqual((new, dup), (0, 1))  # legacy row still deduplicates

    def test_19_show_runs_and_labels_calculation(self):
        p = self.csv([dict(title='IT Support', company='A', description='Remote.', pay_min='20', pay_max='25', pay_period='hour')])
        self.quiet(job_hunter.import_csv, str(p))
        _, out = self.quiet(job_hunter.detail, 1)
        self.assertIn('CALCULATED', out)
        self.assertIn('employer-posted', out)
        self.assertIn('Evidence map', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
