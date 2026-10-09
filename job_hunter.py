#!/usr/bin/env python3
"""NOVA JobHunter Kyle Style v0.6 (Milestone C + BugHunter): offline, standard-library-only prototype."""
import argparse, csv, datetime as dt, hashlib, json, re, sqlite3, os, smtplib, ssl
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from email.message import EmailMessage
from pathlib import Path

import nova_rank, nova_sources, nova_apply, nova_bounty, shutil, time

# JOBHUNTER_HOME lets tests (or a second profile) use a separate data folder.
def home(): return Path(os.environ.get('JOBHUNTER_HOME') or Path(__file__).resolve().parent)
def DB(): return home() / 'jobhunter.sqlite3'
CODE = Path(__file__).resolve().parent
USER_FILES = ('profile.json', 'sources.json', 'resume_facts.json', 'contact.local.json', 'bounty.json')

def ensure_local_files():
    """Zips ship editable files in defaults/. They are copied ONCE if missing, never overwritten."""
    h = home(); h.mkdir(parents=True, exist_ok=True)
    for name in USER_FILES:
        src = CODE / 'defaults' / name
        if not (h / name).exists() and src.exists():
            shutil.copy(src, h / name)
            print(f'Created {name} from defaults/ (edit it freely; updates will not overwrite it).')

def user_file(name):
    ensure_local_files()
    return home() / name
def PROFILE(): return user_file('profile.json')
def EVENTS(): return home() / 'notifications.jsonl'
def EMAIL_QUEUE(): return home() / 'email_outbox.jsonl'
def SOURCES(): return user_file('sources.json')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
 company TEXT NOT NULL, url TEXT, description TEXT NOT NULL,
 pay_min REAL, pay_max REAL, pay_period TEXT, pay_currency TEXT,
 traditional_score INTEGER NOT NULL, exploration_score INTEGER NOT NULL,
 evidence_score INTEGER NOT NULL, final_score INTEGER NOT NULL,
 reasons TEXT NOT NULL, gaps TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'discovered',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
 name TEXT PRIMARY KEY, type TEXT NOT NULL, target TEXT, last_checked_at TEXT, last_ok_at TEXT,
 last_status TEXT, last_new INTEGER, last_dup INTEGER, last_filtered INTEGER, last_invalid INTEGER
);
CREATE TABLE IF NOT EXISTS packets (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, variant TEXT NOT NULL, path TEXT NOT NULL,
 sha256 TEXT NOT NULL, created_at TEXT NOT NULL, approved_at TEXT, approved_sha256 TEXT, approval_note TEXT,
 FOREIGN KEY(job_id) REFERENCES jobs(id)
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, job_id INTEGER, event TEXT NOT NULL,
 details TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(job_id) REFERENCES jobs(id)
);
'''

def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
NEW_COLS = [('pay_min','REAL'),('pay_max','REAL'),('pay_period','TEXT'),('pay_currency','TEXT'),
            # Milestone A (all nullable so v0.1/v0.2 databases migrate in place)
            ('pay_source','TEXT'),('location','TEXT'),('work_mode','TEXT'),('gate','TEXT'),
            ('requirements','TEXT'),('unknowns','TEXT'),('disqualifiers','TEXT'),('evidence_map','TEXT'),
            ('fp_v2','TEXT'),('content_hash','TEXT'),('gate_override','TEXT'),
            # Milestone B: where/when a listing came from
            ('source','TEXT'),('source_type','TEXT'),('external_id','TEXT'),('source_location','TEXT'),
            ('posted_at','TEXT'),('first_seen_at','TEXT'),('last_seen_at','TEXT')]

def connect():
    con = sqlite3.connect(DB())
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute('PRAGMA table_info(jobs)')}
    for name, typ in NEW_COLS:
        if name not in cols: con.execute(f'ALTER TABLE jobs ADD COLUMN {name} {typ}')
    nova_bounty.init(con)
    con.execute('CREATE INDEX IF NOT EXISTS idx_fp_v2 ON jobs(fp_v2)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_content_hash ON jobs(content_hash)')
    # Backfill dedup keys for rows created by older versions.
    for r in con.execute('SELECT id,title,company,url,description FROM jobs WHERE fp_v2 IS NULL').fetchall():
        job = dict(zip(('title','company','url','description'), r[1:]))
        con.execute('UPDATE jobs SET fp_v2=?,content_hash=? WHERE id=?', (fingerprint(job), content_hash(job), r[0]))
    con.commit()
    return con

def load_profile(): return json.loads(PROFILE().read_text(encoding='utf-8'))

TRACKING = re.compile(r'^(utm_.*|ref|refid|src|source|trk|trackingid|gclid|fbclid|mc_[a-z]+|from)$', re.I)

def normalize_url(url):
    url = (url or '').strip()
    if not url: return ''
    parts = urlsplit(url if '://' in url else 'https://' + url)
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not TRACKING.match(k)))
    path = re.sub(r'/+$', '', parts.path) or '/'
    return urlunsplit(('https', re.sub(r'^www\.', '', parts.netloc.lower()), path, query, ''))

def _clean(s): return re.sub(r'\s+', ' ', str(s or '')).strip().lower()

def fingerprint(job):
    """company|title|normalized URL. Tracking params, case, whitespace, trailing / ignored."""
    key = '|'.join((_clean(job.get('company')), _clean(job.get('title')), normalize_url(job.get('url'))))
    return hashlib.sha256(key.encode()).hexdigest()

def content_hash(job):
    """Catches the same posting re-listed under a different URL (or no URL)."""
    desc = re.sub(r'[^a-z0-9]+', ' ', _clean(job.get('description'))).strip()
    key = '|'.join((_clean(job.get('company')), _clean(job.get('title')), desc))
    return hashlib.sha256(key.encode()).hexdigest()

def find_duplicate(con, job):
    fp, ch, legacy = fingerprint(job), content_hash(job), legacy_fingerprint(job)
    row = con.execute('SELECT id FROM jobs WHERE fp_v2=? OR content_hash=? OR fingerprint=? LIMIT 1', (fp, ch, legacy)).fetchone()
    return row[0] if row else None

def legacy_fingerprint(job):
    key = '|'.join(str(job.get(k, '')).strip().lower() for k in ('company','title','url'))
    return hashlib.sha256(key.encode()).hexdigest()

def event(con, job_id, name, details, pending):
    """Audit row goes in the DB transaction; JSONL line is written only after commit."""
    stamp = now()
    con.execute('INSERT INTO audit(job_id,event,details,created_at) VALUES (?,?,?,?)',
                (job_id, name, json.dumps(details), stamp))
    pending.append({'time':stamp,'job_id':job_id,'event':name,'details':details})

def flush_events(pending):
    if not pending: return
    with EVENTS().open('a', encoding='utf-8') as f:
        for rec in pending: f.write(json.dumps(rec)+'\n')
    pending.clear()

def pay(job):
    def number(k):
        raw = str(job.get(k,'') or '').strip().replace('$','').replace(',','')
        if not raw: return None
        try:
            value = float(raw)
            if value < 0: raise ValueError()
            return value
        except ValueError: raise ValueError(f'Invalid {k}: {raw}')
    low, high = number('pay_min'), number('pay_max')
    period = str(job.get('pay_period','') or '').strip().lower()
    currency = str(job.get('pay_currency','USD') or 'USD').strip().upper()
    if period and period not in ('hour','year','month','week'):
        raise ValueError('pay_period must be hour, week, month, or year')
    if low is not None and high is not None and high < low:
        raise ValueError('pay_max below pay_min')
    if (low is not None or high is not None) and not period:
        raise ValueError('pay_period required when pay is supplied')
    return low,high,period,currency

def pay_label(low,high,period,currency='USD'):
    if low is None and high is None: return 'Not disclosed'
    unit={'hour':'hr','year':'yr','month':'mo','week':'wk'}.get(period,period)
    fmt=lambda n: f'{n:,.2f}'.rstrip('0').rstrip('.')
    symbol='$' if currency=='USD' else currency+' '
    if low is not None and high is not None:
        amount=f'{symbol}{fmt(low)}–{symbol}{fmt(high)}'
    elif low is not None: amount=f'{symbol}{fmt(low)}+'
    else: amount=f'Up to {symbol}{fmt(high)}'
    return f'{amount}/{unit} ({currency})'

def send_email(subject,body):
    recipient=os.environ.get('JOBHUNTER_EMAIL_TO','').strip()
    sender=os.environ.get('JOBHUNTER_EMAIL_FROM','').strip()
    password=os.environ.get('JOBHUNTER_SMTP_PASSWORD','')
    host=os.environ.get('JOBHUNTER_SMTP_HOST','smtp.gmail.com')
    port=int(os.environ.get('JOBHUNTER_SMTP_PORT','465'))
    if not (recipient and sender and password):
        print('Email not configured; notification retained locally.')
        return False
    msg=EmailMessage();msg['Subject']=subject;msg['From']=sender;msg['To']=recipient
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL(host,port,context=ssl.create_default_context(),timeout=20) as smtp:
            smtp.login(sender,password);smtp.send_message(msg)
        print('Email sent to configured address.')
        return True
    except (OSError,smtplib.SMTPException) as exc:
        print(f'Email failed ({type(exc).__name__}); notification retained locally.')
        return False

def notify(subject,body):
    with EMAIL_QUEUE().open('a',encoding='utf-8') as f:
        f.write(json.dumps({'time':now(),'subject':subject,'body':body})+'\n')
    return send_email(subject,body)

def score_columns(result):
    req = result['requirements']
    return dict(traditional_score=result['conventional'], exploration_score=result['adjacent'],
                evidence_score=result['evidence_score'], final_score=result['final'],
                reasons=json.dumps(result['reasons']), gaps=json.dumps(result['disqualifiers'] + result['unknowns']),
                gate=result['gate'], requirements=json.dumps(req), unknowns=json.dumps(result['unknowns']),
                disqualifiers=json.dumps(result['disqualifiers']), evidence_map=json.dumps(result['evidence_map']),
                location=req['location'], work_mode=','.join(req['work_modes']) or None)

def ingest_rows(con, rows, profile, pending, source='manual', source_type='csv', verbose=True):
    """Shared by `import` and `run`. Returns (new, duplicates, invalid, new_ids)."""
    new = duplicates = skipped = 0; new_ids = []
    for job in rows:
        job = {k.strip().lower(): (v or '').strip() if isinstance(v, str) else ('' if v is None else str(v))
               for k, v in job.items() if isinstance(k, str)}
        if not job.get('title') or not job.get('company') or not job.get('description'):
            if verbose: print('Skipping row missing title/company/description')
            skipped += 1; continue
        try: low, high, period, currency = pay(job)
        except ValueError as exc:
            if verbose: print(f'Skipping {job["title"]}: {exc}')
            skipped += 1; continue
        pay_src = 'listing_fields' if (low is not None or high is not None) else None
        if pay_src is None:
            txt = nova_rank.extract_pay_text(job['description'])
            if txt:  # employer wrote it in the listing; still not an estimate
                low, high, period, currency, pay_src = txt['pay_min'], txt['pay_max'], txt['pay_period'], txt['pay_currency'], txt['pay_source']
        if pay_src is None: currency = None
        stamp = now()
        dup = find_duplicate(con, job)
        if dup:
            duplicates += 1
            con.execute('UPDATE jobs SET last_seen_at=? WHERE id=?', (stamp, dup))
            if verbose: print(f'Duplicate of #{dup}: {job["title"]} @ {job["company"]}')
            continue
        result = nova_rank.evaluate_job(job, profile)
        cols = score_columns(result)
        status = 'discovered' if result['gate'] == 'pass' else 'needs_review'
        cur = con.execute('''INSERT INTO jobs
          (fingerprint,fp_v2,content_hash,title,company,url,description,pay_min,pay_max,pay_period,pay_currency,pay_source,
           traditional_score,exploration_score,evidence_score,final_score,reasons,gaps,gate,requirements,unknowns,
           disqualifiers,evidence_map,location,work_mode,status,created_at,updated_at,
           source,source_type,external_id,source_location,posted_at,first_seen_at,last_seen_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
           (fingerprint(job),fingerprint(job),content_hash(job),job['title'],job['company'],job.get('url',''),job['description'],
            low,high,period,currency,pay_src,cols['traditional_score'],cols['exploration_score'],cols['evidence_score'],
            cols['final_score'],cols['reasons'],cols['gaps'],cols['gate'],cols['requirements'],cols['unknowns'],
            cols['disqualifiers'],cols['evidence_map'],cols['location'],cols['work_mode'],status,stamp,stamp,
            source,source_type,job.get('external_id') or None,job.get('location') or None,job.get('posted_at') or None,stamp,stamp))
        new += 1; new_ids.append(cur.lastrowid)
        event(con,cur.lastrowid,'JOB_DISCOVERED',{'score':result['final'],'gate':result['gate'],'status':status,'source':source,
              'title':job['title'],'company':job['company'],'pay':pay_label(low,high,period,currency)}, pending)
    return new, duplicates, skipped, new_ids

def import_csv(path):
    profile = load_profile()
    con = connect(); pending = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    new, duplicates, skipped, _ = ingest_rows(con, rows, profile, pending, source='manual:' + Path(path).name)
    con.commit(); flush_events(pending); con.close()
    print(f'Imported {new} new jobs; skipped {duplicates} duplicates; {skipped} invalid rows.')
    # Import alerts are a digest, not one email per listing.
    if new and os.environ.get('JOBHUNTER_EMAIL_IMPORT','0') == '1':
        notify('NOVA JobHunter: new jobs imported', f'{new} new jobs imported. Open Termux and run: python job_hunter.py list --min-score 0')
    return new, duplicates, skipped

def _parse_time(t):
    try: return dt.datetime.fromisoformat(t)
    except (TypeError, ValueError): return None

def run(force=False, only=None, fetch=None, sleep=time.sleep, quiet=False):
    """The start button: check every enabled source, ingest, then print the dashboard."""
    cfg = nova_sources.load_config(SOURCES()); d = cfg['defaults']
    profile = load_profile(); con = connect(); pending = []
    base = home(); results = []; all_new = []; network_calls = 0
    for src in cfg['sources']:
        name, typ = src['name'], src['type']
        if only and name not in only: continue
        if not src.get('enabled', True):
            results.append((name, 'disabled', 0, 0, 0, 0)); continue
        row = con.execute('SELECT last_checked_at FROM sources WHERE name=?', (name,)).fetchone()
        last = _parse_time(row[0]) if row else None
        wait = nova_sources.interval_minutes(src, d)
        floor = nova_sources.HARD_FLOOR_MINUTES if typ in nova_sources.NETWORK_TYPES else 0
        if last:
            age = (dt.datetime.now(dt.timezone.utc) - last).total_seconds() / 60
            limit = floor if force else wait
            if age < limit:
                results.append((name, f'wait {int(limit - age) + 1}m', 0, 0, 0, 0)); continue
        if typ in nova_sources.NETWORK_TYPES:
            if network_calls: sleep(float(d['request_delay_seconds']))
            network_calls += 1
        stamp = now(); target = src.get('path') or src.get('board')
        try:
            rows = nova_sources.fetch_rows(src, base, fetch or nova_sources.http_json, float(d['timeout_seconds']))
            kept, filtered = [], 0
            flt = src.get('filter', {'title_any': 'profile', 'location_any': 'profile'} if typ in nova_sources.NETWORK_TYPES else None)
            for r in rows:
                if nova_sources.passes_filter(r, flt, profile): filtered += 1
                else: kept.append(r)
            n, dup, bad, ids = ingest_rows(con, kept, profile, pending, source=name, source_type=typ, verbose=False)
            status, ok_at = 'ok', stamp; all_new += ids
        except (nova_sources.SourceError, OSError, ValueError, KeyError) as exc:
            n = dup = bad = filtered = 0; status, ok_at = f'error: {str(exc)[:60]}', None
        con.execute('''INSERT INTO sources(name,type,target,last_checked_at,last_ok_at,last_status,last_new,last_dup,last_filtered,last_invalid)
            VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET type=excluded.type,target=excluded.target,
            last_checked_at=excluded.last_checked_at,last_ok_at=COALESCE(excluded.last_ok_at,sources.last_ok_at),
            last_status=excluded.last_status,last_new=excluded.last_new,last_dup=excluded.last_dup,
            last_filtered=excluded.last_filtered,last_invalid=excluded.last_invalid''',
            (name, typ, target, stamp, ok_at, status, n, dup, filtered, bad))
        event(con, None, 'SOURCE_CHECKED', {'source': name, 'status': status, 'new': n, 'dup': dup,
                                            'filtered': filtered, 'invalid': bad}, pending)
        results.append((name, status, n, dup, filtered, bad))
    con.commit(); flush_events(pending); con.close()
    if not quiet: dashboard(results, all_new)
    if all_new and os.environ.get('JOBHUNTER_EMAIL_IMPORT','0') == '1':
        notify('NOVA JobHunter: new jobs found', f'{len(all_new)} new jobs. In Termux run: python job_hunter.py dashboard')
    return results, all_new

def counts(con, high_min=60, unconv_min=60):
    q = lambda sql, *a: con.execute(sql, a).fetchone()[0]
    live = "status NOT IN ('rejected')"
    return {
        'discovered': q(f'SELECT COUNT(*) FROM jobs WHERE {live}'),
        'high': q(f"SELECT COUNT(*) FROM jobs WHERE {live} AND gate='pass' AND final_score>=?", high_min),
        'unconv': q(f"SELECT COUNT(*) FROM jobs WHERE {live} AND COALESCE(gate,'')!='fail' AND exploration_score>=? "
                    "AND exploration_score>=traditional_score+10", unconv_min),
        'prepared': q("SELECT COUNT(*) FROM jobs WHERE status='prepared'"),
        'review': q("SELECT COUNT(*) FROM jobs WHERE status='needs_review'"),
        'action': q("SELECT COUNT(*) FROM jobs WHERE status='action_required'"),
        'submitted': q("SELECT COUNT(*) FROM jobs WHERE status IN ('submitted','interview')"),
        'interview': q("SELECT COUNT(*) FROM jobs WHERE status='interview'"),
    }

def dashboard(results=None, new_ids=()):
    """Phone-width (<= 40 cols) summary."""
    try: d = nova_sources.load_config(SOURCES())['defaults']
    except nova_sources.SourceError: d = dict(nova_sources.DEFAULTS)
    con = connect(); c = counts(con, int(d['high_match_min']), int(d['unconventional_min']))
    W = '-' * 38
    print(f"NOVA JobHunter  {dt.datetime.now().strftime('%m-%d %H:%M')}")
    if results is None:
        results = [(r[0], r[1] or '-', r[2] or 0, r[3] or 0, r[4] or 0, r[5] or 0) for r in
                   con.execute('SELECT name,last_status,last_new,last_dup,last_filtered,last_invalid FROM sources ORDER BY name')]
    if results:
        print(W)
        for name, st, n, dup, flt, bad in results:
            extra = f' +{n} new, {dup} dup' + (f', {flt} filt' if flt else '') + (f', {bad} bad' if bad else '') if st == 'ok' else ''
            print(f' {name[:14]:<14} {st[:22]}{extra}')
    print(W)
    print(f" Discovered     {c['discovered']:>4}" + (f'  (+{len(new_ids)} new)' if new_ids else ''))
    print(f" High match     {c['high']:>4}")
    print(f" Unconventional {c['unconv']:>4}")
    print(f" Prepared       {c['prepared']:>4}")
    print(f" Action needed  {c['review'] + c['action']:>4}  (review {c['review']}, action {c['action']})")
    print(f" Submitted      {c['submitted']:>4}  (interview {c['interview']})")
    print(W)
    if new_ids:
        marks = ','.join('?' * len(new_ids))
        top = con.execute(f"SELECT id,final_score,gate,title,company FROM jobs WHERE id IN ({marks}) "
                          "ORDER BY CASE gate WHEN 'pass' THEN 0 WHEN 'review' THEN 1 ELSE 2 END, final_score DESC LIMIT 5", list(new_ids)).fetchall()
        print(' Top new:')
        for i, sc, g, t, co in top:
            print(f'  #{i} {sc:>3} {(g or "?").upper():<6} {t[:24]}')
            print(f'       @ {co[:28]}')
        print(f' Next: python job_hunter.py show {top[0][0]}')
    elif c['review']:
        print(' Next: python job_hunter.py list --min-score 0')
    con.close()
    return c

def show_sources():
    cfg = nova_sources.load_config(SOURCES()); con = connect()
    for s in cfg['sources']:
        r = con.execute('SELECT last_checked_at,last_ok_at,last_status FROM sources WHERE name=?', (s['name'],)).fetchone()
        n = con.execute('SELECT COUNT(*) FROM jobs WHERE source=?', (s['name'],)).fetchone()[0]
        on = 'on ' if s.get('enabled', True) else 'off'
        print(f"[{on}] {s['name']} ({s['type']}: {s.get('path') or s.get('board')})")
        print(f"      every {nova_sources.interval_minutes(s, cfg['defaults']):.0f}m | jobs {n} | {r[2] if r else 'never checked'}")
        if r: print(f"      checked {r[0]} | last ok {r[1] or '-'}")
    con.close()

def show_evidence():
    prof = load_profile(); idx = nova_rank.build_evidence_index(prof)
    for e in prof.get('evidence', []):
        if 'id' not in e: continue
        rec = next((v for v in idx.values() if v['id'] == e['id']), None)
        st = rec['status'] if rec else e.get('status', 'self_reported')
        flag = ' (DOWNGRADED: missing/invalid ref)' if rec and rec['downgraded'] else ''
        print(f"{e['id']} [{st.upper()}]{flag} {e.get('type','')}")
        print(f"   ref: {e.get('ref') or 'none'}")
        print(f"   skills: {', '.join(e.get('skills', []))}")
        print(f"   {e.get('summary','')}")

def rescore():
    """Re-run Milestone A on every job (use after editing profile.json). Status is not changed."""
    profile = load_profile(); con = connect(); pending = []
    rows = con.execute('SELECT id,title,company,url,description,gate,source_location,pay_source FROM jobs').fetchall()
    for r in rows:
        # derived location is re-extracted from text; only the source-provided location is fed back in
        job = dict(zip(('title','company','url','description'), r[1:5])); job['location'] = r[6] or ''
        result = nova_rank.evaluate_job(job, profile); cols = score_columns(result)
        con.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in cols) + ',updated_at=? WHERE id=?',
                    (*cols.values(), now(), r[0]))
        if r[7] != 'listing_fields':  # re-read pay written in the text; structured fields are never overwritten
            txt = nova_rank.extract_pay_text(r[4])
            con.execute('UPDATE jobs SET pay_min=?,pay_max=?,pay_period=?,pay_currency=?,pay_source=? WHERE id=?',
                        (txt['pay_min'],txt['pay_max'],txt['pay_period'],txt['pay_currency'],txt['pay_source'],r[0]) if txt
                        else (None,None,None,None,None,r[0]))
        if r[5] != result['gate']:
            event(con, r[0], 'GATE_CHANGED', {'from': r[5], 'to': result['gate']}, pending)
    con.commit(); flush_events(pending); con.close()
    print(f'Rescored {len(rows)} jobs.')

def list_jobs(min_score):
    con=connect()
    rows=con.execute('''SELECT id,title,company,traditional_score,exploration_score,
       final_score,status,pay_min,pay_max,pay_period,pay_currency,COALESCE(gate,'?'),pay_source FROM jobs WHERE final_score >= ?
       ORDER BY CASE gate WHEN 'pass' THEN 0 WHEN 'review' THEN 1 WHEN 'fail' THEN 3 ELSE 2 END, final_score DESC,id''',(min_score,)).fetchall()
    for r in rows:
        print(f'#{r[0]} [{r[11].upper():6}] {r[5]:3d} | conv {r[3]:3d} / adj {r[4]:3d} | {r[6]}\n    {r[1]} @ {r[2]} | Pay: {pay_label(r[7],r[8],r[9],r[10])}{" (period assumed)" if r[12]=="listing_text_period_assumed" else ""}')
    if not rows: print(f'No jobs scored {min_score}+. Try --min-score 0.' if min_score > 0 else 'No jobs yet. Run: python job_hunter.py run')
    con.close()

def annualized(low, high, period, hours_per_week=40, weeks=52):
    """Labeled calculation only. Never stored, never shown as employer-posted."""
    mult = {'hour': hours_per_week*weeks, 'week': weeks, 'month': 12, 'year': 1}.get(period)
    if not mult or period == 'year' or (low is None and high is None): return None
    f = lambda n: f'${n*mult:,.0f}' if n is not None else '?'
    return f'{f(low)}–{f(high)}/yr CALCULATED (assumes {hours_per_week} h/wk x {weeks} wk; not employer-stated)'

def detail(job_id, full=False):
    con=connect(); con.row_factory=sqlite3.Row
    row=con.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not row: print('Unknown job ID'); con.close(); return
    J=lambda k: json.loads(row[k]) if row[k] else []
    print(f"#{row['id']} {row['title']} @ {row['company']}")
    print(f"status: {row['status']} | gate: {(row['gate'] or 'not scored (run rescore)').upper()}"
          + (f" | override: {row['gate_override']}" if row['gate_override'] else ''))
    print(f"scores (heuristic): conventional {row['traditional_score']} | adjacent {row['exploration_score']} | "
          f"evidence {row['evidence_score']}% verified | final {row['final_score']}")
    print('url:', row['url'] or '-')
    if row['source']:
        print(f"source: {row['source']} ({row['source_type']}) | first seen {(row['first_seen_at'] or '')[:10]} | "
              f"last seen {(row['last_seen_at'] or '')[:10]}" + (f" | posted {row['posted_at'][:10]}" if row['posted_at'] else ''))
    print('location:', row['location'] or 'not stated', '| work mode:', row['work_mode'] or 'not stated')
    src = {'listing_fields':'employer-posted (listing fields)','listing_text':'employer-posted (in listing text)',
           'listing_text_period_assumed':'employer-posted amount; YEARLY period assumed (not stated)'}.get(row['pay_source'],'')
    print('Pay:', pay_label(row['pay_min'],row['pay_max'],row['pay_period'],row['pay_currency'] or 'USD') + (f' [{src}]' if src else ''))
    a = annualized(row['pay_min'],row['pay_max'],row['pay_period'])
    if a: print('     ', a)
    print('Disqualifiers:'); [print(' x '+d) for d in J('disqualifiers')] or print(' (none found)')
    print('Unknowns / verify:'); [print(' ? '+u) for u in J('unknowns')] or print(' (none)')
    req = json.loads(row['requirements']) if row['requirements'] else {'items': []}
    print('Requirements extracted:')
    for it in req.get('items', []):
        extra = f" {it.get('min_years')}+y" if it['kind']=='years' else (f" {it.get('pct')}%" if it['kind']=='travel' else '')
        print(f"   [{it['level']:11}] {it['kind']}:{it['key']}{extra} -> {it.get('candidate','n/a')}  «{it['source'][:70]}»")
    if not req.get('items'): print('   (none detected — read the listing yourself)')
    print('Evidence map:')
    for e in J('evidence_map'):
        st = e['status'].upper() + ('*' if e.get('downgraded') else '')
        kind = {'demonstrated':'demo','learning_lab':'lab','transferable':'transfer'}.get(e['kind'], e['kind'])
        print(f"   {e['claim'][:16]:<16} {kind:<8} {st:<13} {e.get('id') or 'no ref'}")
    print('   (* = downgraded. Full references: python job_hunter.py evidence)')
    print('Reasons:'); [print(' - '+r) for r in J('reasons')]
    d = row['description']
    if not full and len(d) > 700:
        d = d[:700].rsplit(' ', 1)[0] + f' ... [+{len(row["description"]) - 700} chars: show {job_id} --full]'
    print('Description:', d)
    con.close()

ALLOWED = {'discovered':{'shortlisted','needs_review','rejected'},
           'needs_review':{'shortlisted','discovered','rejected'},'shortlisted':{'prepared','rejected'},
           'prepared':{'submitted','action_required','rejected'},
           'action_required':{'prepared','submitted','rejected'},
           'submitted':{'interview','rejected','action_required'},
           'interview':{'rejected'},'rejected':set()}

def change_status(job_id, status, confirmation='', override=''):
    confirmation=(confirmation or '').strip(); override=(override or '').strip()
    con=connect(); row=con.execute('SELECT status,gate FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not row: con.close(); raise SystemExit('Unknown job ID')
    if status not in ALLOWED.get(row[0],set()):
        con.close(); raise SystemExit(f'Invalid transition {row[0]} -> {status}')
    if status == 'prepared':
        con.close(); raise SystemExit(f'Use: jh prepare {job_id}  (builds the packet, then sets prepared)')
    if status == 'submitted':
        pk = con.execute('SELECT path,approved_sha256 FROM packets WHERE job_id=? ORDER BY id DESC LIMIT 1',(job_id,)).fetchone()
        if not pk or not pk[1]:
            con.close(); raise SystemExit(f'No approved packet. Review it, then: jh approve {job_id}')
        if nova_apply.hash_dir(pk[0]) != pk[1]:
            con.close(); raise SystemExit(f'Packet files changed after approval. Re-check, then: jh approve {job_id}')
    if status == 'submitted' and len(confirmation) < 4:
        con.close(); raise SystemExit('Submission requires a real --confirmation reference from employer/site. This tool NEVER submits jobs.')
    if status == 'shortlisted' and row[1] == 'fail' and not override:
        con.close(); raise SystemExit('Hard-requirement gate FAILED. Read `show` first; to proceed anyway add --override-gate "your reason".')
    pending=[]
    con.execute('UPDATE jobs SET status=?,updated_at=?,gate_override=COALESCE(?,gate_override) WHERE id=?',
                (status,now(),override or None,job_id))
    event(con,job_id,'STATUS_CHANGED',{'from':row[0],'to':status,'confirmation':confirmation or None,
                                       'gate_override':override or None},pending)
    con.commit(); flush_events(pending); con.close()
    print(f'Job #{job_id}: {row[0]} -> {status}')
    if status in ('submitted','action_required','interview'):
        notify(f'NOVA JobHunter: {status.replace("_"," " ).title()} — Job #{job_id}',
               f'Job #{job_id} changed to {status}.\nConfirmation: {confirmation or "None"}\nCheck details in Termux: python job_hunter.py show {job_id}')

def _load_json(name): return json.loads(user_file(name).read_text(encoding='utf-8'))

def job_dict(con, job_id):
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    con.row_factory = None
    if not row: return None
    d = dict(row); d['pay_label'] = pay_label(d['pay_min'], d['pay_max'], d['pay_period'], d['pay_currency'] or 'USD')
    return d

def prepare(job_id, variant=None):
    """Build resume variant + packet for a shortlisted job. Sends nothing."""
    con = connect(); job = job_dict(con, job_id)
    if not job: con.close(); raise SystemExit('Unknown job ID')
    if job['status'] not in ('shortlisted', 'prepared', 'action_required'):
        con.close(); raise SystemExit(f"Job #{job_id} is {job['status']}. Shortlist it first: jh status {job_id} shortlisted")
    facts = _load_json('resume_facts.json'); contact = _load_json('contact.local.json')
    if variant and variant not in facts['variants']:
        con.close(); raise SystemExit(f"Unknown variant. Choose: {', '.join(facts['variants'])}")
    variant, files = nova_apply.build_packet(job, load_profile(), facts, contact, variant)
    folder = home() / 'packets' / f"{job_id:04d}-{nova_apply.slug(job['company'])}-{nova_apply.slug(job['title'])}"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding='utf-8')
    digest = nova_apply.packet_hash(files); pending = []; stamp = now()
    con.execute('INSERT INTO packets(job_id,variant,path,sha256,created_at) VALUES (?,?,?,?,?)',
                (job_id, variant, str(folder), digest, stamp))
    old = job['status']
    if old != 'prepared':
        con.execute('UPDATE jobs SET status=?,updated_at=? WHERE id=?', ('prepared', stamp, job_id))
        event(con, job_id, 'STATUS_CHANGED', {'from': old, 'to': 'prepared', 'confirmation': None}, pending)
    event(con, job_id, 'PACKET_PREPARED', {'variant': variant, 'sha256': digest[:16], 'path': str(folder)}, pending)
    con.commit(); flush_events(pending); con.close()
    print(f'Packet ready (DRAFT, nothing sent): {variant}')
    print(f'  {folder}/packet.md')
    print(f'  {folder}/resume.md')
    print(f'Read:    less {folder}/packet.md')
    print(f'Approve: jh approve {job_id} --note "reviewed"')
    return folder

def approve(job_id, note=''):
    """Records YOUR manual approval of the current packet files. Does not send anything."""
    con = connect()
    pk = con.execute('SELECT id,path FROM packets WHERE job_id=? ORDER BY id DESC LIMIT 1', (job_id,)).fetchone()
    if not pk: con.close(); raise SystemExit(f'No packet yet: jh prepare {job_id}')
    digest = nova_apply.hash_dir(pk[1])
    if not digest: con.close(); raise SystemExit(f'Packet folder missing: {pk[1]}')
    text = (Path(pk[1]) / 'packet.md').read_text(encoding='utf-8')
    if '[EDIT:' in text:
        print('Note: packet.md still has an [EDIT: ...] line in the pitch. Replace it before you paste the pitch anywhere.')
    pending = []
    con.execute('UPDATE packets SET approved_at=?,approved_sha256=?,approval_note=? WHERE id=?', (now(), digest, note or None, pk[0]))
    event(con, job_id, 'PACKET_APPROVED', {'sha256': digest[:16], 'note': note or None}, pending)
    con.commit(); flush_events(pending); con.close()
    print(f'Approved packet for job #{job_id} (fingerprint {digest[:12]}). Nothing was sent.')
    print('Submit it yourself on the employer site, then record the confirmation:')
    print(f'  jh status {job_id} submitted --confirmation "THEIR-CONFIRMATION-ID"')

def gaps(top=10, write=True):
    """Skill Gap Engine: what to learn next, ranked by how many live jobs ask for it."""
    con = connect(); con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT id,title,final_score,requirements,description,evidence_map FROM jobs "
                                         "WHERE status NOT IN ('rejected') AND COALESCE(gate,'') != 'fail'")]
    con.close(); profile = load_profile()
    report = nova_apply.gap_report(rows, profile); labs = nova_apply.lab_to_evidence(rows, profile)
    W = '-' * 38
    print(f'Skill gaps across {len(rows)} live jobs'); print(W)
    if not report: print(' none detected (add more jobs: jh run)')
    for g in report[:top]:
        print(f" {g['name'][:22]:<22} {len(g['jobs']):>2} jobs  {g['area'][:10]}")
        print(f"   {g['resource'][0][:34]}")
    if labs:
        print(W); print(' Lab-only skills employers want')
        print(' (turn into public proof: write-up/repo):')
        for k, n in labs[:5]: print(f'   {k:<20} {n:>2} jobs')
    print(W); print(' Learning targets, not claims. Legal labs only.')
    if write:
        out = home() / 'reports'; out.mkdir(exist_ok=True)
        L = ['# Skill gap report', f'Live jobs analyzed: {len(rows)} (gate FAIL and rejected excluded).',
             'Gaps are learning targets, never resume claims. Practice only on legal training platforms.', '',
             '| Skill / credential | Area / level | Jobs | Job IDs | Practice resource |', '|---|---|---|---|---|']
        for g in report:
            L.append(f"| {g['name']} | {g['area']} | {len(g['jobs'])} | {', '.join('#'+str(i) for i in g['jobs'][:8])} | "
                     f"[{g['resource'][0]}]({g['resource'][1]}) |")
        if labs:
            L += ['', '## Lab-only skills that keep appearing', 'Convert each into public evidence (a write-up or repo), then add it to profile.json evidence with a URL.', '']
            L += [f'- {k}: {n} jobs' for k, n in labs]
        (out / 'skill_gaps.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
        print(f' Saved: {out / "skill_gaps.md"}')
    return report

# ============================================================ BugHunter (jh bb ...)
BB_STATUSES = ('new', 'watching', 'studying', 'skipped')

def bb_cfg():
    p = user_file('bounty.json')
    cfg = dict(nova_bounty.DEFAULT_CFG)
    if p.exists(): cfg.update({k: v for k, v in json.loads(p.read_text(encoding='utf-8')).items() if not k.startswith('_')})
    return cfg

def bb_sync(force=False, fetch=None, sleep=None):
    con = connect()
    res = nova_bounty.sync(con, load_profile(), bb_cfg(), fetch or nova_bounty.http_json, force, sleep)
    con.commit(); con.close()
    print('BugHunter sync (public listings only;'); print('no target was contacted)'); print('-' * 38)
    for plat, st, n, new in res:
        print(f' {plat:<10} {st[:16]:<16}' + (f' {n} progs, +{new} new' if st == 'ok' else ''))
    print('-' * 38); print(' Next: jh bb list')
    return res

def bb_list(mode='final', category=None, kind=None, limit=15, quiet=False):
    order = {'final': 'final', 'beginner': 'beginner', 'strengths': 'strengths', 'reward': 'reward'}[mode]
    where, args = ["status != 'skipped'", "gate != 'fail'"], []
    if category: where.append("categories LIKE ?"); args.append(f'%"{category}"%')
    if kind == 'vdp': where.append('offers_bounty=0')
    if kind == 'bounty': where.append('offers_bounty=1')
    con = connect()
    rows = con.execute(f"SELECT id,name,platform,offers_bounty,beginner,strengths,reward,final,gate,categories,status FROM bb_programs "
                       f"WHERE {' AND '.join(where)} ORDER BY {order} DESC, final DESC, id LIMIT ?", (*args, limit)).fetchall()
    con.close()
    if not quiet:
        if not rows: print('No programs. Run: jh bb sync')
        for r in rows:
            cats = ','.join(sorted(json.loads(r[9] or '{}'))) or 'policy-only'
            print(f"#{r[0]} [{r[8].upper():6}] {r[7]:>3} | beg {r[4]} / you {r[5]} / $ {r[6]}")
            print(f"    {r[1][:30]} ({r[2]}) {'BOUNTY' if r[3] else 'VDP'}")
            print(f"    {cats[:34]}" + ('' if r[10] == 'new' else f' [{r[10]}]'))
    return rows

def _bb_program(con, pid):
    con.row_factory = sqlite3.Row
    r = con.execute('SELECT * FROM bb_programs WHERE id=?', (pid,)).fetchone()
    assets = [dict(a) for a in con.execute('SELECT * FROM bb_assets WHERE program_id=? ORDER BY in_scope DESC,id', (pid,))]
    con.row_factory = None
    if not r: raise SystemExit('Unknown program ID')
    return dict(r), assets

def bb_show(pid, show_all=False):
    con = connect(); p, assets = _bb_program(con, pid); con.close()
    J = lambda k: json.loads(p[k] or '[]')
    print(f"#{p['id']} {p['name']} ({p['platform']})")
    print(f"{'BOUNTY' if p['offers_bounty'] else 'VDP'}" + (f" max {p['max_bounty']:,.0f} {p['currency']}" if p['max_bounty'] else '')
          + f" | safe harbor: {p['safe_harbor'] or 'not stated'} | gate {p['gate'].upper()}")
    print(f"scores: beginner {p['beginner']} | your strengths {p['strengths']} | reward {p['reward']} | final {p['final']}")
    print('official page:', p['url'])
    print(f"snapshot: {(p['snapshot_at'] or '')[:16]} (third-party mirror; may be stale)")
    print('Why:'); [print(' - ' + x) for x in J('reasons')]
    print('Check:'); [print(' ? ' + x) for x in J('unknowns')] or print(' (none)')
    ins = [a for a in assets if a['in_scope']]; outs = [a for a in assets if not a['in_scope']]
    lim = None if show_all else 12
    print(f'In scope ({len(ins)}):'); [print(f"   [{a['category']}] {a['identifier'][:60]}") for a in ins[:lim]]
    if not show_all and len(ins) > 12: print(f'   ...+{len(ins) - 12} (jh bb show {pid} --all)')
    print(f'Out of scope ({len(outs)}):'); [print(f"   [{a['category']}] {a['identifier'][:60]}") for a in outs[:lim]]
    print('Skill gaps:')
    for g in J('gaps'): print(f"   {g['category']}: {g['need']}"); print(f"     {g['resources'][0][0]}")
    print(f'Next: jh bb plan {pid}')

def bb_plan(pid):
    con = connect(); p, assets = _bb_program(con, pid)
    sc = {'beginner': p['beginner'], 'strengths': p['strengths'], 'reward': p['reward'], 'gate': p['gate'],
          'reasons': json.loads(p['reasons']), 'unknowns': json.loads(p['unknowns']), 'gaps': json.loads(p['gaps'])}
    text = nova_bounty.plan_markdown(p, assets, sc, (p['snapshot_at'] or '')[:16])
    folder = home() / 'bugbounty' / 'plans'; folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{pid:04d}-{nova_apply.slug(p['name'])}.md"
    path.write_text(text, encoding='utf-8'); pending = []
    if p['status'] == 'new': con.execute("UPDATE bb_programs SET status='studying' WHERE id=?", (pid,))
    event(con, None, 'BB_PLAN_WRITTEN', {'program_id': pid, 'name': p['name'], 'path': str(path)}, pending)
    con.commit(); flush_events(pending); con.close()
    print(f'Plan written (planning only; no target contacted):'); print(f'  {path}'); print(f'Read: less {path}')
    return path

def bb_scope(pid, target):
    con = connect(); p, assets = _bb_program(con, pid)
    verdict, ins, outs, notes = nova_bounty.scope_check(assets, target); pending = []
    event(con, None, 'BB_SCOPE_CHECK', {'program_id': pid, 'target': target, 'verdict': verdict}, pending)
    con.commit(); flush_events(pending); con.close()
    print(f'{verdict}: {target}')
    for a, m in ins: print(f"  in-scope match ({m}): {a['identifier']}")
    for a, m in outs: print(f"  OUT-OF-SCOPE match ({m}): {a['identifier']}  <- this wins")
    for n in notes: print('  ! ' + n)
    print(f"  Snapshot {(p['snapshot_at'] or '')[:10]} from a third-party mirror. Confirm on {p['url']}")
    print('  This check sends nothing to the target. It is not permission to test.')
    return verdict

def bb_mark(pid, status):
    con = connect(); _bb_program(con, pid); pending = []
    con.execute('UPDATE bb_programs SET status=? WHERE id=?', (status, pid))
    event(con, None, 'BB_STATUS', {'program_id': pid, 'status': status}, pending)
    con.commit(); flush_events(pending); con.close(); print(f'Program #{pid} -> {status}')

def bb_gaps(top=8):
    """BugHunter side of the Skill Gap Engine: what to learn for the best-fit programs."""
    con = connect()
    rows = con.execute("SELECT id,final,gaps FROM bb_programs WHERE gate!='fail' AND status!='skipped' ORDER BY final DESC LIMIT 100").fetchall()
    con.close(); agg = {}
    for pid, fin, g in rows:
        for x in json.loads(g or '[]'):
            a = agg.setdefault(x['need'], {'n': 0, 'cat': x['category'], 'res': x['resources'][0]}); a['n'] += 1
    print(f'BugHunter skill gaps (top {len(rows)} programs)'); print('-' * 38)
    for need, a in sorted(agg.items(), key=lambda kv: -kv[1]['n'])[:top]:
        print(f" {a['n']:>3}x {a['cat']}: {need[:40]}"); print(f"      {a['res'][0]}")
    print('-' * 38); print(' Practice on legal labs before any real program.')
    return agg

def report():
    con=connect()
    for status,n in con.execute('SELECT status,COUNT(*) FROM jobs GROUP BY status ORDER BY status'):
        print(f'{status}: {n}')
    print('gate:', ', '.join(f'{g or "unscored"}={n}' for g,n in con.execute('SELECT gate,COUNT(*) FROM jobs GROUP BY gate')))
    con.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='cmd',required=True)
    x=sub.add_parser('import');x.add_argument('csvfile')
    x=sub.add_parser('list');x.add_argument('--min-score',type=int,default=50)
    x=sub.add_parser('show');x.add_argument('id',type=int)
    x.add_argument('--full',action='store_true',help='Print the whole description')
    x=sub.add_parser('status');x.add_argument('id',type=int)
    x.add_argument('new_status',choices=sorted(set(ALLOWED)|set().union(*ALLOWED.values())))
    x.add_argument('--confirmation',default='')
    x.add_argument('--override-gate',default='',help='Reason for shortlisting despite a failed hard-requirement gate')
    sub.add_parser('report')
    sub.add_parser('rescore',help='Re-evaluate all jobs after editing profile.json')
    x=sub.add_parser('run',help='START: check enabled sources in sources.json, ingest, show dashboard')
    x.add_argument('--force',action='store_true',help='Ignore min interval (network sources still >= 10 min apart)')
    x.add_argument('--only',nargs='+',help='Only these source names')
    sub.add_parser('dashboard',help='Show the dashboard without checking sources')
    sub.add_parser('sources',help='List sources, intervals and last-checked times')
    sub.add_parser('evidence',help='Show profile evidence entries with full references')
    x=sub.add_parser('prepare',help='Build resume variant + application packet (sends nothing)');x.add_argument('id',type=int)
    x.add_argument('--variant',choices=['it_support','qa_software','tech_security'])
    x=sub.add_parser('approve',help='Record your manual approval of the packet (sends nothing)');x.add_argument('id',type=int)
    x.add_argument('--note',default='')
    x=sub.add_parser('gaps',help='Skill Gap Engine: what to learn next');x.add_argument('--top',type=int,default=10)
    bb=sub.add_parser('bb',help='BugHunter: public bug bounty/VDP discovery (never contacts targets)')
    bsub=bb.add_subparsers(dest='bbcmd',required=True)
    y=bsub.add_parser('sync',help='Download public program listings');y.add_argument('--force',action='store_true')
    y=bsub.add_parser('list');y.add_argument('--by',choices=['final','beginner','strengths','reward'],default='final')
    y.add_argument('--category',choices=sorted(set(nova_bounty.CATEGORY.values())));y.add_argument('--vdp',action='store_true')
    y.add_argument('--bounty',action='store_true');y.add_argument('--limit',type=int,default=15)
    y=bsub.add_parser('show');y.add_argument('id',type=int);y.add_argument('--all',action='store_true')
    y=bsub.add_parser('plan',help='Write a planning document (no target contact)');y.add_argument('id',type=int)
    y=bsub.add_parser('scope',help='Offline scope check against the snapshot');y.add_argument('id',type=int);y.add_argument('target')
    y=bsub.add_parser('mark');y.add_argument('id',type=int);y.add_argument('status',choices=BB_STATUSES)
    y=bsub.add_parser('gaps');y.add_argument('--top',type=int,default=8)
    bsub.add_parser('rescore')
    x=sub.add_parser('test-email'); x.add_argument('--to',default='',help='Optional override recipient for this test')
    a=p.parse_args()
    if a.cmd=='import':import_csv(a.csvfile)
    elif a.cmd=='list':list_jobs(a.min_score)
    elif a.cmd=='show':detail(a.id,a.full)
    elif a.cmd=='status':change_status(a.id,a.new_status,a.confirmation,a.override_gate)
    elif a.cmd=='rescore':rescore()
    elif a.cmd=='run':run(a.force,a.only)
    elif a.cmd=='dashboard':dashboard()
    elif a.cmd=='sources':show_sources()
    elif a.cmd=='evidence':show_evidence()
    elif a.cmd=='prepare':prepare(a.id,a.variant)
    elif a.cmd=='approve':approve(a.id,a.note)
    elif a.cmd=='gaps':gaps(a.top)
    elif a.cmd=='bb':
        c=a.bbcmd
        if c=='sync':bb_sync(a.force)
        elif c=='list':bb_list(a.by,a.category,'vdp' if a.vdp else 'bounty' if a.bounty else None,a.limit)
        elif c=='show':bb_show(a.id,a.all)
        elif c=='plan':bb_plan(a.id)
        elif c=='scope':bb_scope(a.id,a.target)
        elif c=='mark':bb_mark(a.id,a.status)
        elif c=='gaps':bb_gaps(a.top)
        elif c=='rescore':
            con=connect();n=nova_bounty.rescore_all(con,load_profile());con.commit();con.close();print(f'Rescored {n} programs.')
    elif a.cmd=='report':report()
    elif a.cmd=='test-email':
        if a.to: os.environ['JOBHUNTER_EMAIL_TO']=a.to
        notify('NOVA JobHunter test email','Your Termux email notification is working. No job application was submitted.')

if __name__=='__main__': main()
