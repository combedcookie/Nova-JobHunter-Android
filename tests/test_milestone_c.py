#!/usr/bin/env python3
"""Milestone C tests: resume variants, packets, approval, Skill Gap Engine. Synthetic jobs only."""
import csv, io, json, os, re, shutil, sqlite3, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import nova_apply as na  # noqa: E402
import job_hunter as jh  # noqa: E402
from test_milestone_a import profile  # noqa: E402

FACTS = json.loads((HERE / 'defaults' / 'resume_facts.json').read_text(encoding='utf-8'))
CONTACT = {'name': 'Test Person', 'city': 'Newark, OH', 'phone': '000-000-0000', 'email': 't@example.com', 'links': []}
CRED_WORDS = re.compile(r"comptia|a\+|network\+|security\+|ccna|cissp|ceh|oscp|itil|bachelor|associate'?s degree|clearance", re.I)


def q(fn, *a, **k):
    buf = io.StringIO()
    with redirect_stdout(buf):
        r = fn(*a, **k)
    return r, buf.getvalue()


class Variants(unittest.TestCase):
    def test_c01_variant_selection(self):
        cases = {'QA Tester': 'qa_software', 'Junior Android Developer': 'qa_software', 'IT Help Desk Technician': 'it_support',
                 'Desktop Support Analyst': 'it_support', 'SOC Analyst Trainee': 'tech_security',
                 'Support Engineer (AMER)': 'tech_security', 'Technical Product Support Specialist': 'tech_security',
                 'Warehouse Associate': 'it_support'}
        self.assertEqual({t: na.choose_variant(t) for t in cases}, cases)

    def test_c02_resume_is_verbatim_and_claims_no_credentials(self):
        corpus = set(na.resume_corpus(FACTS))
        for v in FACTS['variants']:
            text = na.render_resume(FACTS, CONTACT, v)
            for line in text.splitlines():
                if line.startswith('- ') and not line.startswith('- **'):
                    self.assertIn(line[2:], corpus, f'{v}: invented bullet: {line[:60]}')
            self.assertIsNone(CRED_WORDS.search(text), f'{v} mentions a credential')
            self.assertIn('EPA Section 609', text)
            self.assertNotRegex(text, r'(?i)\b\d+\+? years? of (professional )?it\b')

    def test_c03_three_variants_differ(self):
        texts = {v: na.render_resume(FACTS, CONTACT, v) for v in FACTS['variants']}
        self.assertEqual(len(set(texts.values())), 3)
        self.assertEqual(len({t.splitlines()[1] for t in texts.values()}), 3)        # distinct headlines
        qa = texts['qa_software'].split('## Selected')[1].splitlines()[1]
        self.assertIn('Nabluna', qa)                                                 # QA leads with the app


class Packet(unittest.TestCase):
    def row(self, **kw):
        base = dict(id=7, title='IT Support Specialist', company='Acme Health', url='https://acme.example/7', status='shortlisted',
                    gate='review', traditional_score=60, exploration_score=50, location='Columbus, OH', work_mode='onsite',
                    pay_min=None, pay_max=None, pay_source=None, pay_label='Not disclosed', source='manual', last_seen_at='2026-10-09',
                    description='CompTIA A+ required. Windows 11, Active Directory, ticketing. Troubleshooting. Networking.',
                    requirements=json.dumps({'items': [{'kind': 'credential', 'key': 'comptia_a_plus', 'level': 'required',
                                                        'candidate': 'not_met', 'source': 'CompTIA A+ required.'}]}),
                    evidence_map=json.dumps([
                        {'claim': 'troubleshooting', 'kind': 'demonstrated', 'status': 'verified', 'id': 'E2', 'ref': 'resume'},
                        {'claim': 'customer service', 'kind': 'demonstrated', 'status': 'self_reported', 'id': 'E7', 'ref': None},
                        {'claim': 'networking', 'kind': 'learning_lab', 'status': 'verified', 'id': 'E5', 'ref': 'resume'}]),
                    unknowns=json.dumps(['Location Columbus, OH: check commute']),
                    disqualifiers=json.dumps(['credential:comptia_a_plus (required) — not in credentials_held']))
        base.update(kw)
        return base

    def test_c04_missing_credential_only_in_unresolved(self):
        _, files = na.build_packet(self.row(), profile(), FACTS, CONTACT)
        pk = files['packet.md']
        pitch = pk.split('## Pitch draft (edit before use)\n')[1].split('\n## ')[0]
        self.assertNotRegex(pitch, CRED_WORDS)
        self.assertNotRegex(files['resume.md'], CRED_WORDS)
        unresolved = pk.split('## Unresolved questions')[1].split('\n## ')[0]
        self.assertIn('CompTIA A+ (required). You do NOT have this on record', unresolved)
        self.assertIn('Pay is not disclosed', unresolved)

    def test_c05_pitch_claims_only_verified_and_labels_labs(self):
        _, files = na.build_packet(self.row(), profile(), FACTS, CONTACT)
        pitch = files['packet.md'].split('## Pitch draft (edit before use)\n')[1].split('\n## ')[0]
        self.assertIn('IT Support Specialist role at Acme Health', pitch)
        self.assertIn('troubleshooting', pitch)
        self.assertNotIn('customer service', pitch)            # self-reported: not claimed
        self.assertIn('networking in self-directed labs (not professional work)', pitch)
        self.assertIn('[EDIT:', pitch)

    def test_c06_stretch_lists_gaps_with_resources(self):
        _, files = na.build_packet(self.row(), profile(), FACTS, CONTACT)
        st = files['packet.md'].split('## Stretch / skill gaps for this job')[1]
        self.assertIn('CompTIA A+', st)
        self.assertIn('https://www.professormesser.com/', st)
        self.assertIn('active directory', st)
        self.assertNotIn('troubleshooting', st)                 # known skill is not a gap

    def test_c07_contact_only_in_resume(self):
        _, files = na.build_packet(self.row(), profile(), FACTS, CONTACT)
        self.assertIn('000-000-0000', files['resume.md'])
        self.assertNotIn('000-000-0000', files['packet.md'])

    def test_c08_variant_override_and_period_assumed(self):
        v, files = na.build_packet(self.row(pay_min=60000, pay_max=70000, pay_source='listing_text_period_assumed'),
                                   profile(), FACTS, CONTACT, 'qa_software')
        self.assertEqual(v, 'qa_software')
        self.assertIn('Pay period was assumed yearly', files['packet.md'])


class Flow(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='jh_c_'))
        os.environ['JOBHUNTER_HOME'] = str(self.dir)
        for k in ('JOBHUNTER_EMAIL_TO', 'JOBHUNTER_EMAIL_FROM', 'JOBHUNTER_SMTP_PASSWORD', 'JOBHUNTER_EMAIL_IMPORT'):
            os.environ.pop(k, None)
        (self.dir / 'profile.json').write_text(json.dumps(profile(work_authorized_us=True)), encoding='utf-8')
        (self.dir / 'contact.local.json').write_text(json.dumps(CONTACT), encoding='utf-8')
        p = self.dir / 'jobs.csv'
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['title', 'company', 'url', 'description'])
            w.writeheader()
            w.writerow(dict(title='IT Support Specialist', company='A', url='', description='Remote. Troubleshooting. Windows 11 and Active Directory. Ticketing.'))
            w.writerow(dict(title='QA Tester', company='B', url='', description='Remote. Python testing. SQL and Selenium. Active Directory a plus.'))
            w.writerow(dict(title='Network Engineer', company='C', url='', description='Remote. CCNA required. Active Directory.'))
        q(jh.import_csv, str(p))

    def tearDown(self):
        os.environ.pop('JOBHUNTER_HOME', None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_c09_defaults_copied_once_never_overwritten(self):
        self.assertTrue((self.dir / 'resume_facts.json').exists())    # copied on first use
        self.assertEqual(json.loads((self.dir / 'contact.local.json').read_text())['name'], 'Test Person')  # not overwritten
        (self.dir / 'sources.json').write_text('{"sources": []}')
        jh.ensure_local_files()
        self.assertEqual((self.dir / 'sources.json').read_text(), '{"sources": []}')

    def test_c10_prepare_requires_shortlist_and_manual_prepared_blocked(self):
        with self.assertRaises(SystemExit):
            q(jh.prepare, 1)
        q(jh.change_status, 1, 'shortlisted')
        with self.assertRaises(SystemExit):
            q(jh.change_status, 1, 'prepared')
        folder, out = q(jh.prepare, 1)
        self.assertIn('nothing sent', out)
        self.assertTrue((folder / 'packet.md').exists() and (folder / 'resume.md').exists())
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        self.assertEqual(con.execute('SELECT status FROM jobs WHERE id=1').fetchone()[0], 'prepared')
        ev = [r[0] for r in con.execute('SELECT event FROM audit WHERE job_id=1')]
        con.close()
        self.assertIn('PACKET_PREPARED', ev)

    def test_c11_submit_needs_approval_unchanged_files_and_confirmation(self):
        q(jh.change_status, 1, 'shortlisted')
        folder, _ = q(jh.prepare, 1)
        with self.assertRaises(SystemExit):
            q(jh.change_status, 1, 'submitted', 'CONF-1234')      # not approved
        q(jh.approve, 1, 'looked good')
        (folder / 'packet.md').write_text((folder / 'packet.md').read_text() + '\nedited after approval\n')
        with self.assertRaises(SystemExit):
            q(jh.change_status, 1, 'submitted', 'CONF-1234')      # changed after approval
        q(jh.approve, 1, 're-reviewed')
        with self.assertRaises(SystemExit):
            q(jh.change_status, 1, 'submitted', '')               # no confirmation
        q(jh.change_status, 1, 'submitted', 'CONF-1234')
        con = sqlite3.connect(self.dir / 'jobhunter.sqlite3')
        self.assertEqual(con.execute('SELECT status FROM jobs WHERE id=1').fetchone()[0], 'submitted')
        con.close()

    def test_c12_gap_report_ranks_and_excludes_failed(self):
        report, out = q(jh.gaps, 10)
        by = {g['name']: g for g in report}
        self.assertEqual(len(by['active directory']['jobs']), 2)   # job C failed the gate (CCNA) -> excluded
        self.assertNotIn('CCNA', by)
        self.assertIn('sql', by)
        self.assertTrue(by['active directory']['resource'][1].startswith('https://'))
        self.assertTrue((self.dir / 'reports' / 'skill_gaps.md').exists())
        self.assertIn('Learning targets, not claims', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
