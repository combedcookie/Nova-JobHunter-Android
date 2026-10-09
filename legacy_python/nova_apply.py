#!/usr/bin/env python3
"""NOVA JobHunter Milestone C: resume variants, application packets, Skill Gap Engine.

Template-only (no AI model). Truthfulness rules enforced in code:
  * Resume bullets come verbatim from resume_facts.json. Variants only select/reorder.
  * The pitch only names the employer/title from the listing and only claims skills
    whose evidence is VERIFIED; lab skills are explicitly labeled as lab work.
  * A credential/degree the listing asks for and you don't hold appears ONLY under
    "Unresolved questions", never as a claim.
  * Nothing is sent. Approval is a local record; `submitted` still needs a real
    confirmation reference from the employer.
"""
import hashlib, json, re
from pathlib import Path

VARIANT_RULES = [  # first match wins; title only
    ('qa_software', r'\b(qa|quality|test|tester|testing|sdet|developer|android|mobile|software engineer|programmer)\b'),
    ('it_support', r'\b(help ?desk|service desk|desktop|it support|it technician|computer technician|field technician)\b'),
    ('tech_security', r'\b(security|soc|cyber\w*|technical support|tech support|product support|application support|'
                      r'support engineer|support specialist|support analyst|trainee|apprentice)\b'),
]

CRED_LABEL = {'comptia_a_plus': 'CompTIA A+', 'comptia_network_plus': 'CompTIA Network+',
              'comptia_security_plus': 'CompTIA Security+', 'ccna': 'CCNA', 'cissp': 'CISSP', 'ceh': 'CEH',
              'oscp': 'OSCP', 'itil': 'ITIL', 'aws_certification': 'an AWS certification',
              'microsoft_certification': 'a Microsoft certification', 'google_it_support_cert': 'Google IT Support Certificate',
              'ase_certification': 'ASE certification', 'epa_609': 'EPA 609', 'cdl': 'a CDL',
              'bachelors_degree': "a bachelor's degree", 'associates_degree': "an associate's degree",
              'masters_degree': "a master's degree", 'high_school': 'a high school diploma',
              'security_clearance': 'a security clearance', 'drivers_license': "a driver's license"}

# Skills employers commonly list that are NOT in your profile yet. term -> (area, resource name, url)
R = {
    'messer': ('Professor Messer (free CompTIA courses)', 'https://www.professormesser.com/'),
    'mslearn': ('Microsoft Learn', 'https://learn.microsoft.com/training/'),
    'pwsh': ('Microsoft Learn: PowerShell', 'https://learn.microsoft.com/powershell/'),
    'snow': ('ServiceNow Developer Program (free instance)', 'https://developer.servicenow.com/'),
    'sql': ('SQLBolt', 'https://sqlbolt.com/'),
    'selenium': ('Selenium documentation', 'https://www.selenium.dev/documentation/'),
    'mdn': ('MDN Learn web development', 'https://developer.mozilla.org/en-US/docs/Learn'),
    'aws': ('AWS Skill Builder', 'https://skillbuilder.aws/'),
    'portswigger': ('PortSwigger Web Security Academy', 'https://portswigger.net/web-security'),
    'otw': ('OverTheWire wargames', 'https://overthewire.org/wargames/'),
    'thm': ('TryHackMe', 'https://tryhackme.com/'),
    'docker': ('Docker Get Started', 'https://docs.docker.com/get-started/'),
    'jira': ('Atlassian Jira guides', 'https://www.atlassian.com/software/jira/guides'),
    'android': ('Android Developers courses', 'https://developer.android.com/courses'),
    'pytest': ('pytest documentation', 'https://docs.pytest.org/'),
    'netacad': ('Cisco Networking Academy', 'https://www.netacad.com/'),
    'k8s': ('Kubernetes tutorials', 'https://kubernetes.io/docs/tutorials/'),
    'gha': ('GitHub Actions docs', 'https://docs.github.com/actions'),
}
SKILL_CATALOG = {
    'windows': ('IT support', 'mslearn'), 'windows 10': ('IT support', 'mslearn'), 'windows 11': ('IT support', 'mslearn'),
    'active directory': ('IT support', 'mslearn'), 'group policy': ('IT support', 'mslearn'),
    'microsoft 365': ('IT support', 'mslearn'), 'office 365': ('IT support', 'mslearn'), 'intune': ('IT support', 'mslearn'),
    'azure': ('Cloud', 'mslearn'), 'powershell': ('IT support', 'pwsh'), 'macos': ('IT support', 'messer'),
    'ticketing': ('Ticketing', 'snow'), 'servicenow': ('Ticketing', 'snow'), 'zendesk': ('Ticketing', 'snow'),
    'itil': ('IT support', 'snow'), 'printers': ('IT support', 'messer'), 'voip': ('Networking', 'messer'),
    'dhcp': ('Networking', 'messer'), 'tcp/ip': ('Networking', 'messer'), 'vpn': ('Networking', 'messer'),
    'routing': ('Networking', 'netacad'), 'switching': ('Networking', 'netacad'), 'firewall': ('Networking', 'netacad'),
    'sql': ('Software/QA', 'sql'), 'javascript': ('Software/QA', 'mdn'), 'html': ('Software/QA', 'mdn'),
    'rest api': ('Software/QA', 'mdn'), 'api': ('Software/QA', 'mdn'), 'selenium': ('Software/QA', 'selenium'),
    'test automation': ('Software/QA', 'selenium'), 'test cases': ('Software/QA', 'pytest'), 'pytest': ('Software/QA', 'pytest'),
    'regression testing': ('Software/QA', 'pytest'), 'jira': ('Software/QA', 'jira'), 'agile': ('Software/QA', 'jira'),
    'ci/cd': ('Software/QA', 'gha'), 'docker': ('Software/QA', 'docker'), 'kubernetes': ('Cloud', 'k8s'),
    'aws': ('Cloud', 'aws'), 'bash': ('Linux', 'otw'), 'scripting': ('Linux', 'otw'),
    'siem': ('Security', 'thm'), 'splunk': ('Security', 'thm'), 'incident response': ('Security', 'thm'),
    'vulnerability': ('Security', 'thm'), 'owasp': ('Security', 'portswigger'), 'web application security': ('Security', 'portswigger'),
    'authentication': ('Security', 'portswigger'), 'authorization': ('Security', 'portswigger'),
}
CRED_RESOURCE = {'comptia_a_plus': 'messer', 'comptia_network_plus': 'messer', 'comptia_security_plus': 'messer',
                 'ccna': 'netacad', 'itil': 'snow', 'aws_certification': 'aws', 'microsoft_certification': 'mslearn'}


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')[:40] or 'job'


def choose_variant(title):
    t = (title or '').lower()
    for name, pat in VARIANT_RULES:
        if re.search(pat, t):
            return name
    return 'it_support'


# ------------------------------------------------------------ resume variant
def render_resume(facts, contact, variant):
    v = facts['variants'][variant]
    order = v['tag_order']

    def rank(b):
        hits = [order.index(t) for t in b['tags'] if t in order]
        return min(hits) if hits else len(order)

    out = [f"# {contact.get('name', 'NAME')}", v['headline'], '',
           ' | '.join(x for x in (contact.get('city'), contact.get('phone'), contact.get('email')) if x)]
    if contact.get('links'):
        out.append(' | '.join(contact['links']))
    out += ['', '## Technical Profile', v['summary'], '', '## Core Technologies']
    for g in v['skill_order']:
        out.append(f"- **{g}:** {', '.join(facts['skills'][g])}")
    out += ['', '## Selected Software & Engineering Projects']
    by_name = {p['name']: p for p in facts['projects']}
    for name in v['projects']:
        p = by_name[name]
        out.append(f"**{p['name']}** | {p['role']} | {p['dates']}")
        for b in sorted(p['bullets'], key=rank)[:3]:
            out.append(f"- {b['text']}")
        out.append('')
    out.append('## Professional Experience')
    for e in facts['experience']:
        where = f"{e['company']} - {e['location']}" if e.get('location') else e['company']
        out.append(f"**{e['title']}** | {where} | {e['dates']}")
        for b in sorted(e['bullets'], key=rank):
            out.append(f"- {b['text']}")
        out.append('')
    out += ['## Education & Certification'] + [f'- {x}' for x in facts['education'] + facts['certifications']]
    return '\n'.join(out) + '\n'


def resume_corpus(facts):
    """Every sentence the resume actually contains (used by truthfulness tests)."""
    parts = [b['text'] for p in facts['projects'] for b in p['bullets']]
    parts += [b['text'] for e in facts['experience'] for b in e['bullets']]
    parts += [x for g in facts['skills'].values() for x in g] + facts['education'] + facts['certifications']
    return parts


# ------------------------------------------------------------ packet pieces
def pitch(job, evidence_map, variant_label, background=''):
    verified = [e['claim'] for e in evidence_map if e['status'] == 'verified' and e['kind'] != 'learning_lab']
    labs = [e['claim'] for e in evidence_map if e['kind'] == 'learning_lab' and e['status'] == 'verified']
    lines = [f"I'm applying for the {job['title']} role at {job['company']}."]
    if verified:
        lines.append('From the listing, the parts my resume backs up are: ' + ', '.join(verified[:6]) + '.')
    if background:
        lines.append(background)
    if labs:
        lines.append('I have also practiced ' + ', '.join(labs[:4]) + ' in self-directed labs (not professional work).')
    lines.append('[EDIT: one sentence on why this company/team specifically, from something you read on their site.]')
    return ' '.join(lines)


def unresolved(job_row, req, unknowns, disqualifiers):
    q = ['Is the posting still open? (last seen: ' + (job_row.get('last_seen_at') or 'unknown')[:10] + ')']
    if not job_row.get('pay_min') and not job_row.get('pay_max'):
        q.append('Pay is not disclosed. Ask or check before applying.')
    elif job_row.get('pay_source') == 'listing_text_period_assumed':
        q.append('Pay period was assumed yearly; confirm.')
    for it in req.get('items', []):
        if it.get('candidate') in ('not_met', 'unknown') and it['key'] in CRED_LABEL:
            q.append(f"Listing mentions {CRED_LABEL[it['key']]} ({it['level']}). You do NOT have this on record; "
                     'do not imply it. Decide whether to apply anyway.')
    q += [d for d in disqualifiers if not d.endswith('(override if wrong)')]
    q += [u for u in unknowns]
    seen, out = set(), []
    for x in q:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


def stretch_items(req, text, profile):
    """Per-job skill gaps with legal practice resources."""
    from nova_rank import build_evidence_index
    idx = build_evidence_index(profile)
    # Learning skills only count as "known" when a verified evidence entry backs them.
    known = {s.lower() for s in profile['skills']['demonstrated'] + profile.get('transferable_skills', [])}
    known |= {s.lower() for s in profile['skills']['learning'] if idx.get(s.lower(), {}).get('status') == 'verified'}
    out = []
    for it in req.get('items', []):
        if it.get('candidate') in ('not_met', 'unknown') and it['key'] in CRED_RESOURCE:
            out.append((CRED_LABEL.get(it['key'], it['key']), it['level'], R[CRED_RESOURCE[it['key']]]))
    low = ' ' + re.sub(r'[^a-z0-9+#/]+', ' ', (text or '').lower()) + ' '
    hits = [t for t in SKILL_CATALOG
            if t not in known and re.search(r'(?<![a-z0-9])' + re.escape(t) + r'(?![a-z0-9])', low)]
    hits = [t for t in hits if not any(t != o and t in o for o in hits)]   # "windows" inside "windows 11"
    out += [(t, SKILL_CATALOG[t][0], R[SKILL_CATALOG[t][1]]) for t in hits]
    return out


def build_packet(job_row, profile, facts, contact, variant=None):
    """Return (variant, {filename: text}). Pure function; caller writes files."""
    variant = variant or choose_variant(job_row['title'])
    v = facts['variants'][variant]
    req = json.loads(job_row['requirements'] or '{}')
    ev = json.loads(job_row['evidence_map'] or '[]')
    unk = json.loads(job_row['unknowns'] or '[]')
    dq = json.loads(job_row['disqualifiers'] or '[]')
    resume = render_resume(facts, contact, variant)
    st = stretch_items(req, job_row['description'], profile)
    L = [f"# Application packet: {job_row['title']} @ {job_row['company']}", '',
         'STATUS: DRAFT. Nothing has been sent. Review everything, then run `jh approve ' + str(job_row['id']) + '`.', '',
         '## Listing', f"- Job #{job_row['id']} | gate {str(job_row.get('gate') or '?').upper()} | "
                       f"conventional {job_row['traditional_score']} / adjacent {job_row['exploration_score']} (heuristic)",
         f"- URL: {job_row.get('url') or 'none'}", f"- Source: {job_row.get('source') or 'manual'}",
         f"- Location: {job_row.get('location') or 'not stated'} | mode: {job_row.get('work_mode') or 'not stated'}",
         f"- Pay: {job_row.get('pay_label', 'Not disclosed')}", '',
         f"## Resume variant: {v['label']} (`resume.md`)", '',
         '## Evidence map (what backs each claim)']
    for e in ev:
        tag = 'LAB ONLY' if e['kind'] == 'learning_lab' else e['kind']
        L.append(f"- {e['claim']}: {e['status'].upper()} ({tag}) -> {e.get('id') or 'no evidence entry'}"
                 + (f" [{e['ref']}]" if e.get('ref') else ''))
    if not ev:
        L.append('- (no profile skills matched this listing)')
    L += ['', '## Pitch draft (edit before use)', pitch(job_row, ev, v['label'], facts.get('pitch_background', '')), '',
          '## Unresolved questions'] + [f'- [ ] {q}' for q in unresolved(job_row, req, unk, dq)]
    L += ['', '## Stretch / skill gaps for this job']
    if st:
        L.append('Gaps are learning targets, not things to claim. Practice only on legal training labs.')
        L += [f"- {name} ({area}): {res[0]} {res[1]}" for name, area, res in st]
    else:
        L.append('- none detected')
    L += ['', '## Before you approve', '- [ ] Resume has nothing you cannot back up in an interview',
          '- [ ] Pitch edited; [EDIT] line replaced', '- [ ] Unresolved questions answered or accepted',
          '- [ ] You will submit manually on the employer site and save the confirmation number']
    return variant, {'packet.md': '\n'.join(L) + '\n', 'resume.md': resume}


def packet_hash(files):
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b'\0' + files[name].encode('utf-8') + b'\0')
    return h.hexdigest()


def hash_dir(path):
    path = Path(path)
    files = {p.name: p.read_text(encoding='utf-8') for p in path.glob('*.md')}
    return packet_hash(files) if files else None


# ------------------------------------------------------------ skill gap engine
def gap_report(rows, profile):
    """rows: dicts with id, final_score, requirements, description. Returns sorted gaps."""
    gaps = {}
    for r in rows:
        req = json.loads(r['requirements'] or '{}')
        seen = set()
        for name, area, res in stretch_items(req, r['description'], profile):
            if name in seen:
                continue
            seen.add(name)
            g = gaps.setdefault(name, {'name': name, 'area': area, 'resource': res, 'jobs': [], 'weight': 0, 'required': 0})
            g['jobs'].append(r['id'])
            g['weight'] += max(1, r['final_score'] or 0)
            if area in ('required',):
                g['required'] += 1
    return sorted(gaps.values(), key=lambda g: (-g['required'], -len(g['jobs']), -g['weight'], g['name']))


def lab_to_evidence(rows, profile):
    """Lab-only skills that keep showing up in listings: turn them into public proof."""
    labs = {s.lower() for s in profile['skills']['learning']}
    counts = {}
    for r in rows:
        for e in json.loads(r['evidence_map'] or '[]'):
            if e['kind'] == 'learning_lab' and e['claim'] in labs:
                counts[e['claim']] = counts.get(e['claim'], 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])
