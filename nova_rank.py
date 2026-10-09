#!/usr/bin/env python3
"""NOVA JobHunter Milestone A: requirement extraction, evidence map, hard gate.

Standard library only (Termux-safe). Everything here is a rule-based HEURISTIC.
Scores are ranking signals, not probabilities. Nothing is ever upgraded to
"verified" unless the profile evidence entry is verified AND has a reference.
"""
import re

# ---------------------------------------------------------------- text utils
PREF_RE = re.compile(r'\b(preferred|nice[- ]to[- ]have|a plus|bonus|desired|desirable|'
                     r'ideally|advantageous|helpful)\b', re.I)
REQ_RE = re.compile(r'\b(required|requires?|must|minimum|mandatory|essential|'
                    r'need to have|needs to have)\b', re.I)
# "No degree required", "Certification not required", "without prior experience"
NEG_CLAUSE_RE = re.compile(
    r'\b(not|no)\b[^.;]{0,40}?\b(required|needed|necessary|mandatory)\b'
    r'|\bno\s+(prior\s+|previous\s+)?(experience|degree|certifications?)\b'
    r'|\bnot\s+(a\s+)?requirement\b', re.I)
NEG_WORDS = {'no', 'not', 'non', 'without', 'never'}
HEADER_PREF = re.compile(r'^\s*(preferred( qualifications| skills)?|nice[- ]to[- ]have|bonus( points)?|pluses)\s*:', re.I)
HEADER_REQ = re.compile(r'^\s*(requirements|required( qualifications| skills)?|minimum qualifications|'
                        r'must[- ]haves?|qualifications)\s*:', re.I)

WORD_NUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
            'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}


def norm(s):
    return ' ' + re.sub(r'[^a-z0-9+#.]+', ' ', (s or '').lower()) + ' '


def clauses(text):
    """Split a description into (clause_text, level) with section/marker context.

    level is 'required', 'preferred', or 'unspecified'. Negated clauses get
    level 'not_required' so they never become requirements.
    """
    out = []
    section = 'unspecified'
    for line in re.split(r'[\n\r]+|(?<=[.;!?])\s+|\s*[•·]\s*|\s+-\s+', text or ''):
        line = line.strip()
        if not line:
            continue
        if HEADER_PREF.match(line):
            section = 'preferred'
            line = HEADER_PREF.sub('', line)
        elif HEADER_REQ.match(line):
            section = 'required'
            line = HEADER_REQ.sub('', line)
        parts = [line]
        if PREF_RE.search(line) and REQ_RE.search(line):
            parts = [p for p in re.split(r',|\bbut\b|\bwhile\b|\bwhereas\b', line) if p.strip()]
        for part in parts:
            if NEG_CLAUSE_RE.search(part):
                level = 'not_required'
            elif PREF_RE.search(part):
                level = 'preferred'
            elif REQ_RE.search(part):
                level = 'required'
            else:
                level = section
            out.append((part.strip(), level))
    return out


def term_hits(text, terms):
    """Whole-word/phrase matches, skipping ones negated by the 3 preceding words."""
    found = []
    for clause, _ in clauses(text):
        t = norm(clause)
        for term in terms:
            pat = r'(?<![a-z0-9+#])' + re.escape(norm(term).strip()) + r'(?![a-z0-9+#])'
            for m in re.finditer(pat, t):
                before = t[:m.start()].split()[-3:]
                if NEG_WORDS & set(before):
                    continue
                if term not in found:
                    found.append(term)
                break
    return found


def title_hits(title, keywords):
    """Word-boundary title matching (v0.1 used substring: 'qa' matched 'squad')."""
    t = norm(title)
    return [k for k in keywords
            if re.search(r'(?<![a-z0-9+#])' + re.escape(k.lower()) + r'(?![a-z0-9+#])', t)]


# ------------------------------------------------------- requirement catalog
CREDENTIALS = [
    ('comptia_a_plus', r'(?<![\w])(?:comptia\s+)?a\+(?!\w)|\bcomptia a plus\b'),
    ('comptia_network_plus', r'\bnetwork\+|\bnetwork plus\b'),
    ('comptia_security_plus', r'\bsecurity\+|\bsecurity plus\b'),
    ('ccna', r'\bccna\b'),
    ('cissp', r'\bcissp\b'),
    ('ceh', r'\bceh\b|certified ethical hacker'),
    ('oscp', r'\boscp\b'),
    ('itil', r'\bitil\b'),
    ('aws_certification', r'\baws certified\b|\baws certification\b'),
    ('microsoft_certification', r'\bmcsa\b|\bmicrosoft certified\b|\baz-\d{3}\b|\bmd-\d{3}\b'),
    ('google_it_support_cert', r'google it support (professional )?certificate'),
    ('ase_certification', r'\base certifi(ed|cation)\b'),
    ('epa_609', r'\bepa\s*(section\s*)?609\b'),
    ('cdl', r'\bcdl\b|commercial driver'),
]
DEGREES = [  # (key, rank, regex)
    ('masters_degree', 4, r"\bmaster'?s\b|\bm\.?s\.? degree\b|\bmba\b"),
    ('bachelors_degree', 3, r"\bbachelor'?s?\b|\bb\.?s\.? in\b|\bb\.?a\.? in\b|\b(4|four)[- ]year degree\b|\bcollege degree\b"),
    ('associates_degree', 2, r"\bassociate'?s? degree\b|\b(2|two)[- ]year degree\b"),
    ('high_school', 1, r'\bhigh school\b|\bged\b'),
]
EDU_RANK = {'none': 0, 'high_school': 1, 'associates': 2, 'associates_degree': 2,
            'bachelors': 3, 'bachelors_degree': 3, 'masters': 4, 'masters_degree': 4}
IT_CONTEXT = re.compile(r'\b(help ?desk|service desk|desktop|technical support|tech support|software|'
                        r'qa|quality assurance|testing|development|developer|programming|'
                        r'network(ing)?|security|cybersecurity|systems? admin\w*|cloud|linux|windows|'
                        r'active directory|sysadmin|it support|engineering)\b', re.I)
MECH_CONTEXT = re.compile(r'\b(mechanic(al)?|diesel|automotive|repair|field service|equipment|'
                          r'maintenance|technician)\b', re.I)
YEARS_RE = re.compile(
    r'(?<![\w.])(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*'
    r'(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*)?\+?\s*(?:years?|yrs?)\b', re.I)
SHIFTS = [('day', r'\bday shifts?\b|\bfirst shift\b|\b1st shift\b'),
          ('night', r'\bnight shifts?\b|\bovernight\b|\bthird shift\b|\b3rd shift\b'),
          ('evening', r'\bevening shifts?\b|\bsecond shift\b|\b2nd shift\b'),
          ('weekend', r'\bweekends?\b'),
          ('on_call', r'\bon[- ]call\b'),
          ('rotating', r'\brotating (shifts?|schedule)\b'),
          ('24x7', r'\b24\s*/\s*7\b|\b24x7\b')]
STATE_RE = re.compile(r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*),\s*(A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|'
                      r'M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b')
LOC_STOP = {'onsite', 'on', 'site', 'remote', 'hybrid', 'in', 'based', 'located', 'office', 'location',
            'role', 'position', 'job', 'near', 'the', 'our', 'downtown', 'at', 'from', 'fully', 'must'}
PAY_RE = re.compile(
    r'\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?\s*(?:(?:-|–|—|to)\s*\$?\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?)?\s*'
    r'(?:/|per|an|a)\s*(hour|hr|year|yr|annually|annum|week|wk|month|mo)\b', re.I)
PAY_RANGE_BARE = re.compile(r'\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?\s*(?:-|–|—|to)\s*\$?\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?', re.I)
PERIOD = {'hour': 'hour', 'hr': 'hour', 'year': 'year', 'yr': 'year', 'annually': 'year',
          'annum': 'year', 'week': 'week', 'wk': 'week', 'month': 'month', 'mo': 'month'}


def _num(s):
    return WORD_NUM.get(s.lower()) if s.lower() in WORD_NUM else int(s)


def extract_requirements(job):
    """Return a structured, explainable requirement record for one listing."""
    title = str(job.get('title', '') or '')
    desc = str(job.get('description', '') or '')
    text = title + '. ' + desc
    items = []

    def add(kind, key, level, clause, **extra):
        if level == 'not_required':
            return
        for it in items:  # keep the strongest level for duplicate keys
            if it['kind'] == kind and it['key'] == key:
                rank = {'required': 3, 'unspecified': 2, 'preferred': 1}
                if rank[level] > rank[it['level']]:
                    it.update(level=level, source=clause[:160], **extra)
                return
        items.append(dict(kind=kind, key=key, level=level, source=clause[:160], **extra))

    for clause, level in clauses(desc):
        low = clause.lower()
        flexible = bool(re.search(r'or equivalent|equivalent experience|in lieu of', low))
        for key, pat in CREDENTIALS:
            if re.search(pat, low):
                add('credential', key, level, clause)
        for key, rank, pat in DEGREES:
            if re.search(pat, clause, re.I):
                add('education', key, level, clause, rank=rank, flexible=flexible)
                break
        if re.search(r'\bclearance\b', low):
            add('clearance', 'security_clearance', level, clause)
        if re.search(r"\bdriver'?s licen[sc]e\b|\bvalid licen[sc]e\b", low):
            add('license', 'drivers_license', level, clause)
        for m in YEARS_RE.finditer(clause):
            lo = _num(m.group(1))
            scope = 'it' if IT_CONTEXT.search(clause) else ('mechanical' if MECH_CONTEXT.search(clause) else 'unclear')
            add('years', 'years_' + scope, level, clause, min_years=lo,
                max_years=int(m.group(2)) if m.group(2) else None, scope=scope)
        if re.search(r'authori[sz]ed to work|work authori[sz]ation|eligible to work', low):
            add('work_auth', 'work_authorized_us', 'required' if level == 'unspecified' else level, clause)
        if re.search(r'(no|not|unable to|cannot|will not)\s+(provide\s+|offer\s+)?(visa\s+)?sponsor', low) \
                or re.search(r'without (visa )?sponsorship', low):
            add('work_auth', 'no_sponsorship', 'required', clause)
        if re.search(r'\bu\.?s\.? citizen(ship)?\b', low):
            add('work_auth', 'us_citizen', 'required' if level == 'unspecified' else level, clause)
        tm = re.search(r'travel[^.;]{0,30}?(\d{1,3})\s*%|(\d{1,3})\s*%[^.;]{0,20}travel', low)
        if tm:
            add('travel', 'travel', 'required', clause, pct=int(tm.group(1) or tm.group(2)))
        elif re.search(r'\bno travel\b', low):
            pass
        elif re.search(r'\btravel (is )?required\b|\bmust (be able to )?travel\b|\bfrequent travel\b', low):
            add('travel', 'travel', 'required', clause, pct=None)
        for key, pat in SHIFTS:
            if re.search(pat, low) and not re.search(r'\bno (' + pat + ')', low):
                add('shift', key, 'required' if level == 'unspecified' else level, clause)

    low = text.lower()
    modes = []
    if re.search(r'\b(fully |100% )?remote\b', low) and not re.search(r'\bnot remote\b|\bno remote\b', low):
        modes.append('remote')
    if re.search(r'\bhybrid\b', low):
        modes.append('hybrid')
    if re.search(r'\bon[- ]?site\b|\bin[- ]office\b|\bin[- ]person\b', low):
        modes.append('onsite')
    loc = str(job.get('location', '') or '').strip()
    if not loc:
        m = STATE_RE.search(desc)
        city = m.group(1) if m else ''
        words = city.split()
        while words and words[0].lower() in LOC_STOP:
            words.pop(0)
        loc = f"{' '.join(words)}, {m.group(2)}" if words else ''

    return {'items': items, 'work_modes': modes, 'location': loc or None, 'pay_text': extract_pay_text(desc)}


def extract_pay_text(desc):
    """Pay explicitly written in the listing text. Never an estimate."""
    def val(n, k):
        if n is None:
            return None
        v = float(n.replace(',', ''))
        return v * 1000 if k else v
    m = PAY_RE.search(desc or '')
    if m:
        lo, hi = val(m.group(1), m.group(2)), val(m.group(3), m.group(4) or m.group(2))
        return {'pay_min': lo, 'pay_max': hi, 'pay_period': PERIOD[m.group(5).lower()],
                'pay_currency': 'USD', 'pay_source': 'listing_text', 'quote': m.group(0)}
    # "$86,500 — $146,400 USD" with no period: only accept clearly annual-sized ranges, and say so.
    m = PAY_RANGE_BARE.search(desc or '')
    if m:
        lo, hi = val(m.group(1), m.group(2)), val(m.group(3), m.group(4) or m.group(2))
        if lo >= 10000 and hi >= lo:
            return {'pay_min': lo, 'pay_max': hi, 'pay_period': 'year', 'pay_currency': 'USD',
                    'pay_source': 'listing_text_period_assumed', 'quote': m.group(0)}
    return None


# ------------------------------------------------------------- evidence map
def build_evidence_index(profile):
    """skill -> best evidence record. Verified requires status AND reference."""
    index = {}
    for ev in profile.get('evidence', []):
        status = ev.get('status', 'self_reported')
        ref = str(ev.get('ref', '') or '').strip()
        typ = ev.get('type', '')
        downgraded = False
        if status == 'verified':
            ok = bool(ref)
            if typ == 'portfolio' and not re.match(r'https?://', ref):
                ok = False
            if not ok:
                status, downgraded = 'self_reported', True
        if status not in ('verified', 'self_reported'):
            status = 'self_reported'
        rec = {'id': ev.get('id', '?'), 'type': typ, 'status': status, 'ref': ref or None,
               'summary': ev.get('summary', ''), 'downgraded': downgraded}
        for skill in ev.get('skills', []):
            cur = index.get(skill.lower())
            if cur is None or (cur['status'] != 'verified' and status == 'verified'):
                index[skill.lower()] = rec
    return index


def evidence_for(skill, index):
    rec = index.get(skill.lower())
    if rec:
        return rec
    return {'id': None, 'type': None, 'status': 'self_reported', 'ref': None,
            'summary': 'Listed in profile only; no evidence entry', 'downgraded': False}


# ----------------------------------------------------------------- the gate
def check_item(item, facts, index):
    """Return (state, note). state: met_verified|met_unverified|unknown|not_met."""
    kind, key = item['kind'], item['key']
    if kind == 'credential':
        held = [c.lower() for c in facts.get('credentials_held', [])]
        if key in held:
            ev = index.get(key)
            return ('met_verified' if ev and ev['status'] == 'verified' else 'met_unverified',
                    'in credentials_held')
        return 'not_met', 'not in credentials_held'
    if kind == 'education':
        edu = facts.get('education_highest')
        if edu is None:
            return 'unknown', 'education_highest not set in profile'
        have = EDU_RANK.get(str(edu).lower(), 0)
        if have >= item['rank']:
            ev = index.get(str(edu).lower())
            return ('met_verified' if ev and ev['status'] == 'verified' else 'met_unverified'), f'profile education: {edu}'
        if item.get('flexible'):
            return 'unknown', 'listing allows equivalent experience; human judgment needed'
        return 'not_met', f'profile education: {edu}'
    if kind == 'clearance':
        c = facts.get('security_clearance')
        if c is None:
            return 'unknown', 'security_clearance not set'
        return ('met_unverified', f'clearance: {c}') if str(c).lower() not in ('none', 'no', 'false') \
            else ('not_met', 'no clearance held')
    if kind == 'license':
        v = facts.get('drivers_license')
        return ('unknown', 'drivers_license not set') if v is None else \
            (('met_unverified', 'has license') if v else ('not_met', 'no license'))
    if kind == 'years':
        field = {'it': 'years_professional_it', 'mechanical': 'years_mechanical_diagnostics'}.get(item['scope'])
        if field is None:
            return 'unknown', f"{item['min_years']}+ years of unclear scope; read the listing"
        have = facts.get(field)
        if have is None:
            return 'unknown', f'{field} not set'
        return ('met_unverified', f'{field}={have}') if have >= item['min_years'] \
            else ('not_met', f"{field}={have} < {item['min_years']}")
    if kind == 'work_auth':
        if key == 'no_sponsorship':
            v = facts.get('needs_sponsorship')
            return ('unknown', 'needs_sponsorship not set') if v is None else \
                (('not_met', 'you need sponsorship') if v else ('met_unverified', 'no sponsorship needed'))
        field = 'us_citizen' if key == 'us_citizen' else 'work_authorized_us'
        v = facts.get(field)
        return ('unknown', f'{field} not set') if v is None else \
            (('met_unverified', f'{field}=true') if v else ('not_met', f'{field}=false'))
    if kind == 'travel':
        mx = facts.get('max_travel_pct')
        if mx is None or item.get('pct') is None:
            return 'unknown', 'travel amount or your max_travel_pct unknown'
        return ('met_unverified', f'{item["pct"]}% <= {mx}%') if item['pct'] <= mx \
            else ('not_met', f'{item["pct"]}% > your max {mx}%')
    if kind == 'shift':
        ok, no = facts.get('shifts_ok') or [], facts.get('shifts_no') or []
        if key in no:
            return 'not_met', f'{key} is in your shifts_no'
        if key in ok:
            return 'met_unverified', f'{key} acceptable'
        return 'unknown', f'{key} shift: not in shifts_ok or shifts_no'
    return 'unknown', 'unhandled requirement type'


HARD_KINDS = {'credential', 'education', 'clearance', 'license', 'years', 'work_auth', 'travel', 'shift'}


def evaluate_job(job, profile):
    """Full Milestone A evaluation. Returns a dict (JSON-serializable)."""
    facts = profile.get('candidate_facts', {})
    index = build_evidence_index(profile)
    req = extract_requirements(job)
    text = ' '.join(str(job.get(k, '') or '') for k in ('title', 'description'))
    title = str(job.get('title', '') or '')

    # --- conventional fit: role title + demonstrated skills, weighted by evidence
    demo = term_hits(text, profile['skills']['demonstrated'])
    labs = [s for s in term_hits(text, profile['skills']['learning']) if s not in demo]
    role_hits = [r['name'] for r in profile['target_roles'] if title_hits(title, r['title_keywords'])]
    evidence_map, reasons = [], []
    conv = 10 + (20 if role_hits else 0)
    for s in demo:
        ev = evidence_for(s, index)
        conv += 9 if ev['status'] == 'verified' else 6
        evidence_map.append({'claim': s, 'kind': 'demonstrated', **ev})
    for s in labs:
        conv += 2
        evidence_map.append({'claim': s, 'kind': 'learning_lab', **evidence_for(s, index),
                             'note': 'Lab/learning only, NOT work experience'})
    conv = min(100, conv)

    # --- adjacent / unconventional fit: transferable skills + adjacent titles
    bridge = term_hits(text, profile['transferable_skills'])
    adj_title = title_hits(title, profile['adjacent_title_keywords'])
    adj = min(100, 10 + 12 * len(bridge) + 4 * len(demo) + (20 if adj_title else 0))
    for s in bridge:
        if s not in demo:
            evidence_map.append({'claim': s, 'kind': 'transferable', **evidence_for(s, index)})

    verified = sum(1 for e in evidence_map if e['status'] == 'verified')
    evidence_score = round(100 * verified / len(evidence_map)) if evidence_map else 0

    # --- hard requirement gate
    disqualifiers, unknowns, gate_rows = [], [], []
    gate = 'pass'
    for it in req['items']:
        if it['kind'] not in HARD_KINDS:
            continue
        state, note = check_item(it, facts, index)
        it['candidate'] = state
        it['note'] = note
        gate_rows.append(it)
        label = f"{it['kind']}:{it['key']} ({it['level']}) — {note}"
        if it['level'] == 'preferred':
            if state in ('not_met', 'unknown'):
                reasons.append('Preferred, not blocking: ' + label)
            continue
        if state == 'not_met':
            if it['level'] == 'required':
                disqualifiers.append(label)
                gate = 'fail'
            else:
                disqualifiers.append('PROBABLE (wording unclear): ' + label)
                if gate == 'pass':
                    gate = 'review'
        elif state in ('unknown', 'met_unverified'):
            unknowns.append(('Verify: ' if state == 'met_unverified' else 'Unknown: ') + label)
            if gate == 'pass' and (state == 'unknown' or it['kind'] in ('credential',)):
                gate = 'review'

    probable = [d for d in disqualifiers if d.startswith('PROBABLE')]
    if gate == 'review' and len(probable) >= 2:
        gate = 'fail'  # several unmet hard items: unclear wording no longer gives benefit of the doubt
        disqualifiers.append(f'{len(probable)} probable hard-requirement misses; treated as FAIL (override if wrong)')
    if not req['work_modes']:
        unknowns.append('Work mode (remote/hybrid/onsite) not stated')
    else:
        allowed = [m for m in req['work_modes'] if facts.get(m + '_ok', True)]
        if not allowed and facts:
            disqualifiers.append(f"Work mode {req['work_modes']} not acceptable per profile")
            gate = 'fail'
    if 'remote' not in req['work_modes']:
        if not req['location']:
            unknowns.append('Location not stated')
        elif facts.get('location'):
            city = req['location'].split(',')[0].strip().lower()
            near = [c.lower() for c in facts.get('commute_ok_cities', [])]
            if city not in near:
                mx = facts.get('max_commute_minutes')
                unknowns.append(f"Location {req['location']} vs your {facts['location']}: check commute"
                                + (f' (max {mx} min)' if mx else ''))

    reasons[:0] = [
        f"Target role title match: {', '.join(role_hits) or 'none'}",
        f"Adjacent title match: {', '.join(adj_title) or 'none'}",
        f"Demonstrated skill overlap: {', '.join(demo) or 'none'}",
        f"Learning/lab overlap (not work experience): {', '.join(labs) or 'none'}",
        f"Transferable overlap: {', '.join(bridge) or 'none'}",
        f"Evidence: {verified}/{len(evidence_map)} matched claims backed by verified references",
        'Heuristic score only; not a probability of being hired or eligible.',
    ]
    final = round(0.55 * conv + 0.45 * adj)
    if gate == 'fail':
        final = min(final, 20)

    return {'conventional': conv, 'adjacent': adj, 'evidence_score': evidence_score,
            'final': final, 'gate': gate, 'reasons': reasons, 'unknowns': unknowns,
            'disqualifiers': disqualifiers, 'evidence_map': evidence_map,
            'requirements': {**req, 'items': gate_rows + [i for i in req['items'] if i not in gate_rows]}}
