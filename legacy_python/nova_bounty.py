#!/usr/bin/env python3
"""NOVA BugHunter: public bug bounty / VDP program discovery, scoring, planning, scope check.

Standard library only. Shares JobHunter's SQLite DB, profile.json evidence, and audit log.

WHAT THIS DOES: reads PUBLIC program listings, scores them for you, writes a study/plan
document, and checks whether a target appears in a program's published scope snapshot.

WHAT THIS NEVER DOES: send any request to a program's targets. No scanning, fuzzing,
crawling, brute force, or exploit code. Any active testing is a separate, manual action
you take yourself after verifying scope and rules on the official program page.

Data sources (public):
  bounty-targets-data  https://github.com/arkadiyt/bounty-targets-data  (third-party mirror of
                       HackerOne / Bugcrowd / Intigriti / YesWeHack public program scopes)
  disclose.io diodb    https://github.com/disclose/diodb  (vulnerability disclosure policies)
A mirror can be stale or wrong. The official program page is always the authority.
"""
import datetime as dt, gzip, ipaddress, json, re, urllib.error, urllib.request
from urllib.parse import urlsplit

UA = 'NOVA-BugHunter/0.1 (personal research; low volume)'
BTD = 'https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/'
FEEDS = {
    'hackerone': BTD + 'hackerone_data.json',
    'bugcrowd': BTD + 'bugcrowd_data.json',
    'intigriti': BTD + 'intigriti_data.json',
    'yeswehack': BTD + 'yeswehack_data.json',
    'diodb': 'https://raw.githubusercontent.com/disclose/diodb/master/program-list.json',
}
DEFAULT_CFG = {'platforms': ['hackerone', 'bugcrowd', 'intigriti', 'yeswehack', 'diodb'],
               'min_interval_minutes': 360, 'timeout_seconds': 60}
HARD_FLOOR_MINUTES = 30

CATEGORY = {  # raw asset type (lowercased) -> category
    'url': 'web', 'wildcard': 'web', 'website': 'web', 'web-application': 'web',
    'api': 'api',
    'google_play_app_id': 'android', 'other_apk': 'android', 'android': 'android', 'mobile-application-android': 'android',
    'apple_store_app_id': 'ios', 'testflight': 'ios', 'other_ipa': 'ios', 'ios': 'ios', 'mobile-application-ios': 'ios',
    'mobile-application': 'mobile',
    'source_code': 'source_code',
    'ip_address': 'network', 'cidr': 'network', 'network': 'network', 'iprange': 'network',
    'hardware': 'hardware', 'iot': 'hardware', 'device': 'hardware',
    'downloadable_executables': 'executable', 'application': 'executable', 'windows_app_store_app_id': 'executable',
    'smart_contract': 'smart_contract', 'ai_model': 'ai_model', 'ai-model': 'ai_model',
}

# category -> (profile skills that count as a fit, gap description, resources)
RES = {
    'portswigger': ('PortSwigger Web Security Academy', 'https://portswigger.net/web-security'),
    'pswapi': ('PortSwigger: API testing', 'https://portswigger.net/web-security/api-testing'),
    'pswllm': ('PortSwigger: Web LLM attacks', 'https://portswigger.net/web-security/llm-attacks'),
    'mastg': ('OWASP MASTG (mobile testing guide)', 'https://mas.owasp.org/MASTG/'),
    'wstg': ('OWASP Web Security Testing Guide', 'https://owasp.org/www-project-web-security-testing-guide/'),
    'codereview': ('OWASP Code Review Guide', 'https://owasp.org/www-project-code-review-guide/'),
    'iot': ('OWASP IoT Project', 'https://owasp.org/www-project-internet-of-things/'),
    'sc': ('OWASP Smart Contract Top 10', 'https://owasp.org/www-project-smart-contract-top-10/'),
    'h101': ('Hacker101 (free, HackerOne)', 'https://www.hacker101.com/'),
    'bcu': ('Bugcrowd University', 'https://www.bugcrowd.com/hackers/bugcrowd-university/'),
    'thm': ('TryHackMe', 'https://tryhackme.com/'),
}
SKILL_FIT = {
    'web': (['burp suite', 'api testing', 'web/api testing'], 'HTTP, auth/session and access-control testing', ['portswigger', 'wstg', 'h101']),
    'api': (['api testing', 'python', 'burp suite'], 'API authentication/authorization testing', ['pswapi', 'portswigger']),
    'android': (['android', 'kotlin', 'jetpack compose', 'android studio'], 'Android app security testing (storage, IPC, network)', ['mastg']),
    'mobile': (['android', 'kotlin'], 'Mobile app security testing', ['mastg']),
    'ios': ([], 'iOS app security testing (needs Apple hardware)', ['mastg']),
    'source_code': (['python', 'kotlin', 'git'], 'Secure code review', ['codereview']),
    'network': (['nmap', 'networking', 'tcp/ip'], 'Network/infrastructure testing (high risk of going out of scope)', ['thm']),
    'hardware': (['hardware', 'electrical', 'diagnostics'], 'Hardware/IoT security (firmware, interfaces)', ['iot']),
    'executable': ([], 'Desktop binary reverse engineering', ['thm']),
    'smart_contract': ([], 'Smart contract auditing (Solidity)', ['sc']),
    'ai_model': (['python'], 'LLM/AI application attacks (prompt injection etc.)', ['pswllm']),
    'other': ([], 'Read the scope text; unclear asset type', ['h101']),
}
ACTIVE_TOOL_WORDS = re.compile(r'\b(nmap|sqlmap|ffuf|gobuster|dirb|nikto|masscan|hydra|nuclei|wpscan|metasploit|burp intruder)\s+-', re.I)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


# ------------------------------------------------------------------ fetch
def http_json(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            return json.loads(raw.decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'HTTP {e.code}')
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(f'{type(e).__name__}: {str(e)[:80]}')


# ------------------------------------------------------------------ normalize
def _cat(raw):
    return CATEGORY.get(str(raw or '').strip().lower(), 'other')


DOMAINISH = re.compile(r'^(https?://)?(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?$', re.I)


def _asset(identifier, raw_type, in_scope, bounty=None, note=''):
    ident = str(identifier or '').strip()
    cat = _cat(raw_type)
    if cat == 'other' and DOMAINISH.match(ident):
        cat = 'web'          # e.g. HackerOne OTHER "*.example.com"
    return {'identifier': ident, 'raw_type': str(raw_type or ''), 'category': cat,
            'in_scope': 1 if in_scope else 0, 'bounty': None if bounty is None else (1 if bounty else 0),
            'note': str(note or '')[:300]}


def normalize(platform, data):
    """Platform JSON -> list of program dicts (common shape)."""
    out = []
    if platform == 'hackerone':
        for p in data:
            t = p.get('targets') or {}
            assets = [_asset(a.get('asset_identifier'), a.get('asset_type'), True, a.get('eligible_for_bounty'), a.get('instruction'))
                      for a in t.get('in_scope', []) if a.get('eligible_for_submission', True)]
            assets += [_asset(a.get('asset_identifier'), a.get('asset_type'), False) for a in t.get('out_of_scope', [])]
            out.append({'key': 'hackerone:' + p['handle'], 'platform': 'hackerone', 'name': p.get('name') or p['handle'],
                        'url': p.get('url') or f"https://hackerone.com/{p['handle']}", 'policy_url': p.get('url'),
                        'offers_bounty': bool(p.get('offers_bounties')), 'max_bounty': None, 'currency': 'USD',
                        'safe_harbor': None, 'open': p.get('submission_state') == 'open', 'public': True,
                        'flags': {'response_efficiency': p.get('response_efficiency_percentage'), 'swag': p.get('offers_swag')},
                        'assets': assets})
    elif platform == 'bugcrowd':
        for p in data:
            t = p.get('targets') or {}
            assets = [_asset(a.get('target') or a.get('uri'), a.get('type'), True) for a in t.get('in_scope', [])]
            assets += [_asset(a.get('target') or a.get('uri'), a.get('type'), False) for a in t.get('out_of_scope', [])]
            mp = p.get('max_payout')
            out.append({'key': 'bugcrowd:' + p['url'].rstrip('/').split('/')[-1], 'platform': 'bugcrowd', 'name': p['name'].strip(),
                        'url': p['url'], 'policy_url': p['url'], 'offers_bounty': bool(mp), 'max_bounty': mp or None, 'currency': 'USD',
                        'safe_harbor': p.get('safe_harbor'), 'open': True, 'public': True,
                        'flags': {'allows_disclosure': p.get('allows_disclosure')}, 'assets': assets})
    elif platform == 'intigriti':
        for p in data:
            t = p.get('targets') or {}
            assets = [_asset(a.get('endpoint'), a.get('type'), True, note=a.get('description')) for a in t.get('in_scope', [])]
            assets += [_asset(a.get('endpoint'), a.get('type'), False, note=a.get('description')) for a in t.get('out_of_scope', [])]
            mx = (p.get('max_bounty') or {}).get('value') or 0
            out.append({'key': 'intigriti:' + p['handle'], 'platform': 'intigriti', 'name': p['name'], 'url': p['url'],
                        'policy_url': p['url'], 'offers_bounty': mx > 0, 'max_bounty': mx or None,
                        'currency': (p.get('max_bounty') or {}).get('currency', 'EUR'), 'safe_harbor': None,
                        'open': p.get('status') == 'open', 'public': p.get('confidentiality_level') == 'public',
                        'flags': {'terms_acceptance_required': p.get('tacRequired'), 'two_factor_required': p.get('twoFactorRequired')},
                        'assets': assets})
    elif platform == 'yeswehack':
        for p in data:
            t = p.get('targets') or {}
            assets = [_asset(a.get('target'), a.get('type'), True) for a in t.get('in_scope', [])]
            assets += [_asset(a.get('target'), a.get('type'), False) for a in t.get('out_of_scope', [])]
            mx = p.get('max_bounty') or 0
            out.append({'key': 'yeswehack:' + p['id'], 'platform': 'yeswehack', 'name': p['name'],
                        'url': f"https://yeswehack.com/programs/{p['id']}", 'policy_url': f"https://yeswehack.com/programs/{p['id']}",
                        'offers_bounty': mx > 0, 'max_bounty': mx or None, 'currency': 'EUR', 'safe_harbor': None,
                        'open': not p.get('disabled'), 'public': bool(p.get('public')), 'flags': {}, 'assets': assets})
    elif platform == 'diodb':
        for p in data:
            if p.get('policy_url_status', 'alive') != 'alive' or not p.get('policy_url'):
                continue
            ob = str(p.get('offers_bounty', '')).lower()
            out.append({'key': 'diodb:' + re.sub(r'[^a-z0-9]+', '-', p['program_name'].lower()).strip('-'), 'platform': 'disclose.io',
                        'name': p['program_name'], 'url': p['policy_url'], 'policy_url': p['policy_url'],
                        'offers_bounty': ob in ('yes', 'partial'), 'max_bounty': None, 'currency': None,
                        'safe_harbor': p.get('safe_harbor') or None, 'open': True, 'public': True,
                        'flags': {'contact_email': p.get('contact_email') or None, 'securitytxt': p.get('securitytxt_url') or None,
                                  'scope_in_policy_only': True}, 'assets': []})
    return out


# ------------------------------------------------------------------ scoring
def score_program(prog, profile):
    """Separate heuristic paths: beginner fit, your-strengths fit, reward. Plus a gate.
    Gate PASS means "worth reading the policy", NEVER "authorized to test"."""
    from nova_rank import build_evidence_index
    idx = build_evidence_index(profile)
    learning = {x.lower() for x in profile['skills'].get('learning', [])}
    verified = {k for k, v in idx.items() if v['status'] == 'verified'}
    have = verified - learning            # demonstrated work
    lab = verified & learning             # lab-only: partial credit, labeled
    cats = {}
    for a in prog['assets']:
        if a['in_scope']:
            cats[a['category']] = cats.get(a['category'], 0) + 1
    reasons, gaps, unknowns = [], [], []

    gate = 'pass'
    if not prog['open'] or not prog['public']:
        gate = 'fail'; reasons.append('Not open/public in snapshot')
    if prog['flags'].get('terms_acceptance_required'):
        unknowns.append('Platform requires accepting program terms before testing')
    if prog['flags'].get('two_factor_required'):
        unknowns.append('Platform requires 2FA on your researcher account')
    if prog['flags'].get('scope_in_policy_only'):
        unknowns.append('Scope is only in the policy text: read it; no machine-readable scope')
    elif not cats:
        unknowns.append('No in-scope assets in snapshot: read the program page')
    sh = (prog.get('safe_harbor') or '').lower()
    if sh in ('', 'none'):
        unknowns.append('Safe harbor not confirmed in data: check the policy')
    if unknowns and gate == 'pass':
        gate = 'review'

    beginner = 30
    if not prog['offers_bounty']:
        beginner += 20; reasons.append('VDP / recognition program: less competition, good first reports')
    else:
        mb = prog.get('max_bounty') or 0
        if mb >= 5000:
            beginner -= 10; reasons.append('High payouts attract experienced hunters (more competition)')
    if sh == 'full':
        beginner += 15; reasons.append('Full safe harbor listed')
    elif sh == 'partial':
        beginner += 7
    wild = sum(1 for a in prog['assets'] if a['in_scope'] and a['identifier'].startswith('*.'))
    if wild:
        beginner += 10; reasons.append(f'{wild} wildcard scope(s): more surface to learn on')
    if cats.get('web') or cats.get('api'):
        beginner += 10
    if set(cats) <= {'network', 'hardware', 'smart_contract', 'executable', 'ios'} and cats:
        beginner -= 20; reasons.append('Only advanced asset types in scope')
    eff = prog['flags'].get('response_efficiency')
    if isinstance(eff, (int, float)) and eff >= 80:
        beginner += 5; reasons.append(f'Responds efficiently ({eff}%)')
    beginner = max(0, min(100, beginner))

    strengths, total_fit = [], 0
    for cat, n in cats.items():
        skills, gap_text, res = SKILL_FIT.get(cat, SKILL_FIT['other'])
        hit = [s for s in skills if s in have]
        lab_hit = [s for s in skills if s in lab]
        if hit:
            strengths.append(f'{cat}: {", ".join(hit)}')
            total_fit += 25 if cat in ('android', 'hardware', 'source_code', 'mobile') else 10
        elif lab_hit:
            strengths.append(f'{cat}: {", ".join(lab_hit)} (LAB ONLY)')
            total_fit += 5
            gaps.append({'category': cat, 'need': gap_text + ' (lab basics only so far)', 'resources': [RES[r] for r in res]})
        else:
            gaps.append({'category': cat, 'need': gap_text, 'resources': [RES[r] for r in res]})
        if cat in ('android', 'mobile', 'web', 'api', 'source_code', 'hardware', 'ai_model') and hit:
            gaps.append({'category': cat, 'need': gap_text + ' (you have the dev base; learn the security side)',
                         'resources': [RES[r] for r in res]})
    strengths_score = min(100, 15 + total_fit)
    if strengths:
        reasons.append('Your verified strengths apply: ' + '; '.join(strengths))

    reward = 0
    if prog['offers_bounty']:
        mb = prog.get('max_bounty') or 0
        reward = 40 + (30 if mb >= 5000 else 15 if mb >= 1000 else 5 if mb else 10)
        if not mb:
            unknowns.append('Bounty amounts not in data')
    final = round(0.6 * beginner + 0.3 * strengths_score + 0.1 * reward)  # beginner-first by design
    if gate == 'fail':
        final = min(final, 10)
    return {'beginner': beginner, 'strengths': strengths_score, 'reward': reward, 'final': final, 'gate': gate,
            'categories': cats, 'reasons': reasons, 'unknowns': unknowns, 'gaps': gaps}


# ------------------------------------------------------------------ scope check (offline, snapshot only)
def _host_path(s):
    s = (s or '').strip()
    if not s:
        return '', ''
    u = urlsplit(s if '://' in s else 'https://' + s)
    return (u.hostname or '').lower().rstrip('.'), (u.path or '/')


def _match(asset, target):
    """Return 'exact' | 'wildcard' | 'path' | 'ip' | None. Only for web/api/network identifiers."""
    ident = asset['identifier'].strip()
    th, tp = _host_path(target)
    try:  # IP / CIDR
        ip = ipaddress.ip_address(th or target.strip())
        try:
            return 'ip' if ip in ipaddress.ip_network(ident, strict=False) else None
        except ValueError:
            return None
    except ValueError:
        pass
    if not th:
        return None
    if ident.startswith('*.') or '://*.' in ident:
        base = ident.split('*.', 1)[1].split('/')[0].lower().rstrip('.')
        return 'wildcard' if th.endswith('.' + base) else None
    ah, ap = _host_path(ident)
    if not ah or ah != th:
        return None
    if ap not in ('', '/') and not tp.startswith(ap.rstrip('*')):
        return None
    return 'path' if ap not in ('', '/') else 'exact'


def scope_check(assets, target):
    """Out-of-scope always wins. Returns (verdict, matched_in, matched_out, notes)."""
    def uniq(pairs):
        seen, out = set(), []
        for a, m in pairs:
            if a['identifier'].lower() not in seen:
                seen.add(a['identifier'].lower()); out.append((a, m))
        return out
    ins = uniq([(a, m) for a in assets if a['in_scope'] for m in [_match(a, target)] if m])
    outs = uniq([(a, m) for a in assets if not a['in_scope'] for m in [_match(a, target)] if m])
    notes = []
    th, _ = _host_path(target)
    for a in assets:
        if a['in_scope'] and a['identifier'].startswith('*.'):
            base = a['identifier'][2:].split('/')[0].lower()
            if th == base:
                notes.append(f'{th} is the apex of wildcard {a["identifier"]}; many programs do NOT include the apex. Check the policy.')
    if outs:
        return 'OUT_OF_SCOPE', ins, outs, notes
    if ins:
        return 'LISTED_IN_SCOPE', ins, outs, notes
    if notes:
        return 'AMBIGUOUS', ins, outs, notes
    return 'NOT_LISTED', ins, outs, notes


# ------------------------------------------------------------------ plan document
def plan_markdown(prog_row, assets, score, snapshot):
    p = prog_row
    L = [f"# BugHunter plan: {p['name']} ({p['platform']})", '',
         'PLANNING DOCUMENT ONLY. NOVA has not contacted any target and never will.',
         'Active testing is a separate manual step you take only after the checklist below is done.', '',
         '## Program', f"- Official page (the authority): {p['url']}",
         f"- Policy: {p['policy_url'] or p['url']}",
         f"- Type: {'bounty' if p['offers_bounty'] else 'VDP / recognition'}"
         + (f" | max {p['max_bounty']:,.0f} {p['currency']}" if p['max_bounty'] else ''),
         f"- Safe harbor (per data): {p['safe_harbor'] or 'not stated'}",
         f"- Scores (heuristic): beginner {score['beginner']} | your strengths {score['strengths']} | reward {score['reward']} | "
         f"gate {score['gate'].upper()}",
         f'- Scope snapshot: {snapshot} via third-party mirror; may be stale', '',
         '## Why it scored this way'] + [f'- {r}' for r in score['reasons']] + \
        [f'- ? {u}' for u in score['unknowns']] + ['', '## In-scope assets (snapshot)']
    ins = [a for a in assets if a['in_scope']]
    for a in ins[:40]:
        L.append(f"- [{a['category']}] {a['identifier']}" + (' (bounty-eligible)' if a['bounty'] else ''))
    if len(ins) > 40:
        L.append(f'- ...and {len(ins) - 40} more (jh bb show {p["id"]} --all)')
    if not ins:
        L.append('- none in data: scope is defined in the policy text')
    outs = [a for a in assets if not a['in_scope']]
    L += ['', '## Out of scope (snapshot): never touch these'] + [f"- [{a['category']}] {a['identifier']}" for a in outs[:40]]
    if not outs:
        L.append('- none listed in data: read the policy; absence here does not mean allowed')
    L += ['', '## Scope verification checklist (do ALL before any testing)',
          '- [ ] Opened the official program page and read the full policy today',
          '- [ ] Target is listed in scope on the official page (not only in this snapshot)',
          f'- [ ] Ran `jh bb scope {p["id"]} <target>` and it says LISTED_IN_SCOPE',
          '- [ ] Noted rules: rate limits, banned techniques, test-account rules, required headers',
          '- [ ] Program allows the testing type you plan (e.g. no automated scanning if banned)',
          '- [ ] Using only your own test accounts and data; never other users',
          '- [ ] Know how to report and the disclosure rules', '',
          '## First session: learn the product as a normal user',
          '- Use the in-scope app/site the way a normal customer would. No tools, no unusual traffic.',
          '- Write down features, roles, and where login, permissions, and payments happen.',
          '- Read the program\'s public disclosed reports (if any) to see what they accept.',
          '- Pick ONE bug class you have practiced in a legal lab, and plan how you would test it within the rules.', '',
          '## Skill gaps and legal practice first']
    if score['gaps']:
        for g in score['gaps']:
            L.append(f"- {g['category']}: {g['need']}")
            L += [f'  - {name}: {url}' for name, url in g['resources']]
    else:
        L.append('- none detected')
    L += ['', '## Report skeleton (fill in only with what you actually observed)',
          '- Title:', '- Asset (exactly as listed in scope):', '- Steps to reproduce:', '- Impact:',
          '- Evidence (your own account/data only):', '- Date/time and your test account:']
    return '\n'.join(L) + '\n'


# ------------------------------------------------------------------ database
SCHEMA = '''
CREATE TABLE IF NOT EXISTS bb_programs (
 id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, platform TEXT NOT NULL, name TEXT NOT NULL,
 url TEXT, policy_url TEXT, offers_bounty INTEGER, max_bounty REAL, currency TEXT, safe_harbor TEXT,
 is_open INTEGER, is_public INTEGER, flags TEXT, categories TEXT, n_in INTEGER, n_out INTEGER,
 beginner INTEGER, strengths INTEGER, reward INTEGER, final INTEGER, gate TEXT,
 reasons TEXT, unknowns TEXT, gaps TEXT, status TEXT NOT NULL DEFAULT 'new',
 first_seen_at TEXT, last_seen_at TEXT, snapshot_at TEXT
);
CREATE TABLE IF NOT EXISTS bb_assets (
 id INTEGER PRIMARY KEY, program_id INTEGER NOT NULL, in_scope INTEGER NOT NULL, category TEXT,
 identifier TEXT, raw_type TEXT, bounty INTEGER, note TEXT, FOREIGN KEY(program_id) REFERENCES bb_programs(id)
);
CREATE INDEX IF NOT EXISTS idx_bb_assets_prog ON bb_assets(program_id);
'''


def init(con):
    con.executescript(SCHEMA)


def upsert(con, prog, sc, stamp):
    row = con.execute('SELECT id FROM bb_programs WHERE key=?', (prog['key'],)).fetchone()
    vals = (prog['platform'], prog['name'], prog['url'], prog['policy_url'], int(prog['offers_bounty']), prog['max_bounty'],
            prog['currency'], prog['safe_harbor'], int(prog['open']), int(prog['public']), json.dumps(prog['flags']),
            json.dumps(sc['categories']), sum(a['in_scope'] for a in prog['assets']),
            sum(1 - a['in_scope'] for a in prog['assets']), sc['beginner'], sc['strengths'], sc['reward'], sc['final'],
            sc['gate'], json.dumps(sc['reasons']), json.dumps(sc['unknowns']), json.dumps(sc['gaps']), stamp, stamp)
    if row:
        pid = row[0]
        con.execute('''UPDATE bb_programs SET platform=?,name=?,url=?,policy_url=?,offers_bounty=?,max_bounty=?,currency=?,
            safe_harbor=?,is_open=?,is_public=?,flags=?,categories=?,n_in=?,n_out=?,beginner=?,strengths=?,reward=?,final=?,
            gate=?,reasons=?,unknowns=?,gaps=?,last_seen_at=?,snapshot_at=? WHERE id=?''', vals + (pid,))
        con.execute('DELETE FROM bb_assets WHERE program_id=?', (pid,))
        new = False
    else:
        cur = con.execute('''INSERT INTO bb_programs(platform,name,url,policy_url,offers_bounty,max_bounty,currency,safe_harbor,
            is_open,is_public,flags,categories,n_in,n_out,beginner,strengths,reward,final,gate,reasons,unknowns,gaps,
            last_seen_at,snapshot_at,key,first_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                          vals + (prog['key'], stamp))
        pid, new = cur.lastrowid, True
    con.executemany('INSERT INTO bb_assets(program_id,in_scope,category,identifier,raw_type,bounty,note) VALUES (?,?,?,?,?,?,?)',
                    [(pid, a['in_scope'], a['category'], a['identifier'], a['raw_type'], a['bounty'], a['note'])
                     for a in prog['assets'] if a['identifier']])
    return pid, new


def sync(con, profile, cfg, fetch=http_json, force=False, sleep=None):
    """Download public listings (rate-limited via the shared `sources` table). Never contacts targets."""
    import time
    sleep = sleep or time.sleep
    results, calls = [], 0
    for plat in cfg['platforms']:
        name = 'bb:' + plat
        row = con.execute('SELECT last_checked_at FROM sources WHERE name=?', (name,)).fetchone()
        if row and row[0]:
            age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(row[0])).total_seconds() / 60
            limit = HARD_FLOOR_MINUTES if force else max(HARD_FLOOR_MINUTES, cfg['min_interval_minutes'])
            if age < limit:
                results.append((plat, f'wait {int(limit - age) + 1}m', 0, 0)); continue
        if calls:
            sleep(2)
        calls += 1
        stamp = now()
        try:
            progs = normalize(plat, fetch(FEEDS[plat], cfg['timeout_seconds']))
            new = 0
            for prog in progs:
                _, is_new = upsert(con, prog, score_program(prog, profile), stamp)
                new += is_new
            status = 'ok'
        except (RuntimeError, KeyError, TypeError, ValueError) as exc:
            progs, new, status = [], 0, f'error: {str(exc)[:60]}'
        con.execute('''INSERT INTO sources(name,type,target,last_checked_at,last_ok_at,last_status,last_new,last_dup,last_filtered,last_invalid)
            VALUES (?,?,?,?,?,?,?,?,0,0) ON CONFLICT(name) DO UPDATE SET last_checked_at=excluded.last_checked_at,
            last_ok_at=COALESCE(excluded.last_ok_at,sources.last_ok_at),last_status=excluded.last_status,
            last_new=excluded.last_new,last_dup=excluded.last_dup''',
                    (name, 'bugbounty', FEEDS[plat], stamp, stamp if status == 'ok' else None, status, new, len(progs) - new))
        results.append((plat, status, len(progs), new))
    return results


def rescore_all(con, profile):
    rows = con.execute('SELECT id,key,platform,name,url,policy_url,offers_bounty,max_bounty,currency,safe_harbor,is_open,is_public,flags '
                       'FROM bb_programs').fetchall()
    for r in rows:
        assets = [dict(zip(('in_scope', 'category', 'identifier', 'raw_type', 'bounty', 'note'), a)) for a in
                  con.execute('SELECT in_scope,category,identifier,raw_type,bounty,note FROM bb_assets WHERE program_id=?', (r[0],))]
        prog = {'key': r[1], 'platform': r[2], 'name': r[3], 'url': r[4], 'policy_url': r[5], 'offers_bounty': bool(r[6]),
                'max_bounty': r[7], 'currency': r[8], 'safe_harbor': r[9], 'open': bool(r[10]), 'public': bool(r[11]),
                'flags': json.loads(r[12] or '{}'), 'assets': assets}
        sc = score_program(prog, profile)
        con.execute('UPDATE bb_programs SET beginner=?,strengths=?,reward=?,final=?,gate=?,reasons=?,unknowns=?,gaps=? WHERE id=?',
                    (sc['beginner'], sc['strengths'], sc['reward'], sc['final'], sc['gate'], json.dumps(sc['reasons']),
                     json.dumps(sc['unknowns']), json.dumps(sc['gaps']), r[0]))
    return len(rows)
