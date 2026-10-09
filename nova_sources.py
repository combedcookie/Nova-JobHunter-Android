#!/usr/bin/env python3
"""NOVA JobHunter Milestone B: permitted job sources (standard library only).

Implemented source types:
  csv         local CSV file (same columns as sample_jobs.csv, optional `location`)
  json        local JSON file: a list of job objects, or {"jobs": [...]}
  greenhouse  Greenhouse public Job Board API  (boards-api.greenhouse.io, no login)
  lever       Lever public Postings API        (api.lever.co/v0/postings, no login)

Deliberately NOT implemented: LinkedIn/Indeed/any site without an official public
API, logins, cookies, CAPTCHA handling, proxy rotation. One request per source per
run, a polite User-Agent, a delay between network sources, and a per-source
minimum check interval enforced from the database.
"""
import csv, html, json, re, time, urllib.request, urllib.error
from pathlib import Path

USER_AGENT = 'NOVA-JobHunter/0.4 (personal job search; low volume; contact via GitHub)'
NETWORK_TYPES = {'greenhouse', 'lever'}
HARD_FLOOR_MINUTES = 10          # --force can never hit a network source more often than this
DEFAULTS = {'min_interval_minutes': 60, 'request_delay_seconds': 2, 'timeout_seconds': 20,
            'high_match_min': 60, 'unconventional_min': 60}
TITLE_EXTRAS = ['support', 'technician', 'help desk', 'helpdesk', 'service desk', 'qa', 'quality',
                'test', 'tester', 'android', 'mobile', 'junior', 'entry', 'associate', 'apprentice',
                'trainee', 'field service', 'desktop']
LOCATION_DEFAULT = ['remote, us', 'remote - us', 'remote (us', 'us remote', 'remote, united states',
                    'united states', 'usa', 'americas', 'north america', 'ohio', ', oh']


class SourceError(Exception):
    pass


# ------------------------------------------------------------------ config
def load_config(path):
    path = Path(path)
    if not path.exists():
        return {'defaults': dict(DEFAULTS), 'sources': []}
    cfg = json.loads(path.read_text(encoding='utf-8'))
    cfg['defaults'] = {**DEFAULTS, **cfg.get('defaults', {})}
    seen = set()
    for s in cfg.get('sources', []):
        if 'name' not in s or 'type' not in s:
            raise SourceError(f'Source missing name/type: {s}')
        if s['name'] in seen:
            raise SourceError(f"Duplicate source name: {s['name']}")
        seen.add(s['name'])
        if s['type'] not in {'csv', 'json'} | NETWORK_TYPES:
            raise SourceError(f"Unknown source type {s['type']!r} for {s['name']}")
    return cfg


def interval_minutes(src, defaults):
    if src['type'] not in NETWORK_TYPES:
        return float(src.get('min_interval_minutes', 0))
    return max(HARD_FLOOR_MINUTES, float(src.get('min_interval_minutes', defaults['min_interval_minutes'])))


# ------------------------------------------------------------------ helpers
def html_to_text(s):
    """Greenhouse content is HTML-escaped HTML; unescape twice, keep list/paragraph breaks."""
    s = html.unescape(html.unescape(s or ''))
    s = re.sub(r'(?i)<\s*(br|/p|/li|/h\d|/div|/ul)\s*/?>', '\n', s)
    s = re.sub(r'(?i)<\s*li[^>]*>', '\n- ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = s.replace('\xa0', ' ')
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in s.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def http_json(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise SourceError(f'HTTP {e.code}')
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SourceError(f'{type(e).__name__}: {str(e)[:80]}')


def _pay_from_lever(rng):
    if not isinstance(rng, dict) or (rng.get('min') is None and rng.get('max') is None):
        return {}
    iv = str(rng.get('interval', '')).lower()
    period = next((p for p in ('hour', 'week', 'month', 'year') if p in iv), '')
    if not period:
        return {}
    return {'pay_min': str(rng.get('min') or ''), 'pay_max': str(rng.get('max') or ''),
            'pay_period': period, 'pay_currency': rng.get('currency') or 'USD'}


# ------------------------------------------------------------------ adapters
def read_csv(src, base):
    path = (base / src['path']) if not Path(src['path']).is_absolute() else Path(src['path'])
    if not path.exists():
        raise SourceError(f'file not found: {path}')
    with open(path, newline='', encoding='utf-8-sig') as f:
        return [dict(r) for r in csv.DictReader(f)]


def read_json(src, base):
    path = (base / src['path']) if not Path(src['path']).is_absolute() else Path(src['path'])
    if not path.exists():
        raise SourceError(f'file not found: {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    rows = data.get('jobs', []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise SourceError('JSON must be a list of jobs or {"jobs": [...]}')
    return [{k: ('' if v is None else str(v)) for k, v in r.items()} for r in rows if isinstance(r, dict)]


def read_greenhouse(src, fetch, timeout):
    board = src['board']
    data = fetch(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true', timeout)
    out = []
    for j in data.get('jobs', []):
        out.append({'title': j.get('title', ''), 'company': src.get('company') or j.get('company_name') or board,
                    'url': j.get('absolute_url', ''), 'description': html_to_text(j.get('content', '')),
                    'location': (j.get('location') or {}).get('name', ''), 'external_id': str(j.get('id', '')),
                    'posted_at': j.get('first_published') or j.get('updated_at') or ''})
    return out


def read_lever(src, fetch, timeout):
    company = src['board']
    data = fetch(f'https://api.lever.co/v0/postings/{company}?mode=json', timeout)
    if not isinstance(data, list):
        raise SourceError('unexpected Lever response')
    out = []
    for j in data:
        parts = [j.get('descriptionPlain', '')]
        for lst in j.get('lists', []) or []:
            parts.append(f"{lst.get('text', '')}:\n" + html_to_text(lst.get('content', '')))
        parts.append(j.get('additionalPlain', ''))
        cat = j.get('categories') or {}
        loc = cat.get('location', '')
        wt = j.get('workplaceType', '')
        desc = '\n'.join(p for p in parts if p)
        if wt and wt.lower() not in desc.lower():
            desc = f'Workplace: {wt}.\n' + desc
        created = j.get('createdAt')
        out.append({'title': j.get('text', ''), 'company': src.get('company') or company,
                    'url': j.get('hostedUrl', ''), 'description': desc, 'location': loc,
                    'external_id': str(j.get('id', '')),
                    'posted_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(created / 1000)) if isinstance(created, (int, float)) else '',
                    **_pay_from_lever(j.get('salaryRange'))})
    return out


def fetch_rows(src, base, fetch=http_json, timeout=20):
    t = src['type']
    if t == 'csv':
        return read_csv(src, base)
    if t == 'json':
        return read_json(src, base)
    if t == 'greenhouse':
        return read_greenhouse(src, fetch, timeout)
    if t == 'lever':
        return read_lever(src, fetch, timeout)
    raise SourceError(f'unknown type {t}')


# ------------------------------------------------------------------ filters
def title_keywords(profile, extra=()):
    kws = [k for r in profile.get('target_roles', []) for k in r['title_keywords']]
    kws += profile.get('adjacent_title_keywords', []) + list(TITLE_EXTRAS) + list(extra)
    return sorted(set(k.lower() for k in kws))


def location_keywords(profile):
    cities = [c.lower() for c in profile.get('candidate_facts', {}).get('commute_ok_cities', [])]
    return LOCATION_DEFAULT + cities


def passes_filter(row, flt, profile):
    """Return None if kept, else a short reason. Local files default to no filter."""
    if not flt:
        return None
    title = ' ' + re.sub(r'[^a-z0-9+#]+', ' ', str(row.get('title', '')).lower()) + ' '
    t_any = flt.get('title_any')
    if t_any:
        kws = title_keywords(profile, flt.get('title_extra', [])) if t_any == 'profile' else [k.lower() for k in t_any]
        if not any(re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', title) for k in kws):
            return 'title'
    t_none = [k.lower() for k in flt.get('title_exclude', ['senior', 'sr', 'staff', 'principal', 'lead',
                                                           'manager', 'director', 'head', 'vp'])]
    if any(re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', title) for k in t_none):
        return 'seniority'
    l_any = flt.get('location_any')
    if l_any:
        loc = str(row.get('location', '') or '').strip().lower()
        kws = location_keywords(profile) if l_any == 'profile' else [k.lower() for k in l_any]
        if not (loc in ('remote', 'anywhere', 'remote first', 'remote-first') or any(k in loc for k in kws)):
            return 'location'
    return None
