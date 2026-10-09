# NOVA JobHunter — Kyle Style v0.1

**Offline Termux prototype. No APK, no API keys, no login cookies, no automatic job submissions.**

## What it does

- Imports job listings from CSV (`title,company,url,description`).
- Runs two independent *heuristic* scoring paths: conventional qualification matching and transferable-skills exploration.
- Runs an evidence gate that flags certain requirements for manual verification.
- Keeps job status, duplicate protection, and an append-only event stream in local SQLite/JSONL.
- Requires an actual confirmation reference before marking an application submitted.

**Important:** This is a rule-based proof of concept, *not* two running LLMs or an actual browser automation agent. Its scores are rough ranking signals, not calibrated probabilities of employment or eligibility. The sample listings are fictional.

## Install on Android / Termux

1. Install Termux from F-Droid (recommended over an outdated Play Store package).
2. Open Termux, then run:

```sh
pkg update
pkg install python
termux-setup-storage
```

3. Download/extract this ZIP to your phone's Downloads folder. If it extracts as `NOVA_JobHunter_KyleStyle`, run:

```sh
cp -r ~/storage/downloads/NOVA_JobHunter_KyleStyle ~/jobhunter
cd ~/jobhunter
```

If Android extracted it into a differently named folder, adjust the source path. Keep the working database under Termux's home directory rather than shared Downloads.

4. Test with fictional sample listings:

```sh
python job_hunter.py import sample_jobs.csv
python job_hunter.py list --min-score 0
python job_hunter.py show 1
python job_hunter.py report
```

5. Move a job through the workflow:

```sh
python job_hunter.py status 1 shortlisted
python job_hunter.py status 1 prepared
```

**Only after actually submitting the application manually and obtaining a confirmation:**

```sh
python job_hunter.py status 1 submitted --confirmation 'example-confirmation-123'
```

6. To import real jobs, create a CSV with the same columns as `sample_jobs.csv` using job descriptions from authorized sources or manual copy/paste:

```sh
python job_hunter.py import my_jobs.csv
python job_hunter.py list --min-score 70
```

## Files

- `job_hunter.py` — executable prototype (Python standard library only)
- `profile.json` — editable skills/targets (review before using; not a verified resume)
- `sample_jobs.csv` — fictional example listings
- `PERPLEXITY_BUILD_BRIEF.md` — instructions for a coding agent to extend the prototype
- `jobhunter.sqlite3` — created after first run; contains your local job records
- `notifications.jsonl` — created on import/status change; local events, **not delivered email**

## Known limitations

- Does not search job boards, control a browser, log in, send emails, create Gmail labels, or submit applications.
- Doesn't extract must-have requirements comprehensively; exact keyword matching can over-score or under-score jobs.
- No pay, commute, location, or remote filtering yet.
- `submitted` means the operator manually recorded a confirmed submission; no site verification is performed.
- No background scheduler or phone push notifications yet.
- The database and event file contain potentially sensitive job-search history; do not publish them.

## Security and compliance

Never put passwords, session cookies, OAuth tokens, or private email credentials into prompts, CSV files, or source control. Later browser integration should use local browser profiles, permissioned tools, human intervention for CAPTCHAs, and platform-compliant automation. Never fabricate qualifications, spam recruiters, or auto-submit without explicit configured consent.

## v0.2 — Salary and email notifications

Job CSVs now accept **optional** `pay_min,pay_max,pay_period,pay_currency` columns. The period must be `hour`, `week`, `month`, or `year`. Missing salary displays **Not disclosed**; the program never estimates or invents compensation. Salary is shown in `list` and `show`. Example sample data is fictional, including pay.

### Gmail notification setup (Termux)

1. Decide which email address should receive alerts. You can use the same Gmail account for sender and recipient.
2. If using Gmail SMTP, enable 2-Step Verification and create a Google **App Password** if your account supports it. Do not use your ordinary Gmail password. Some accounts do not offer App Passwords; use another supported SMTP service or a future OAuth integration in that case.
3. In Termux, enter these commands, replacing only the email addresses:

```sh
export JOBHUNTER_EMAIL_FROM='youraddress@gmail.com'
export JOBHUNTER_EMAIL_TO='youraddress@gmail.com'
read -rs -p 'Gmail app password: ' JOBHUNTER_SMTP_PASSWORD; echo
export JOBHUNTER_SMTP_PASSWORD
python job_hunter.py test-email
```

The password stays in the current shell's environment and is not written into the prototype's configuration. Do not share screenshots or logs showing secrets. Re-enter it after restarting Termux. The default SMTP server is `smtp.gmail.com:465` over TLS. For another provider, set `JOBHUNTER_SMTP_HOST` and `JOBHUNTER_SMTP_PORT`.

**Automatic email triggers:** when you manually change a job's status to `submitted`, `action_required`, or `interview`, the program emails the configured recipient. The `submitted` transition requires an actual confirmation reference. An optional one-email import digest can be enabled with `export JOBHUNTER_EMAIL_IMPORT=1`. Emails are attempted immediately when the CLI command runs; there is no background monitor yet. Events are also recorded in `notifications.jsonl`, and attempted notification text in `email_outbox.jsonl` (an audit record, **not** an automatic retry queue).

Gmail labels/folders are **not** created automatically by this version. You can create Gmail filters using subjects containing `NOVA JobHunter:` to label the notifications. SMTP can send messages but cannot organize your mailbox; a later Gmail API/OAuth feature can do that.

**Privacy:** Never paste cookies, Gmail app passwords, or access tokens into Perplexity, ChatGPT, or repository files.

## v0.3 — Milestone A: credible ranking

New file `nova_rank.py` (standard library only) does the reasoning; `job_hunter.py` stores and displays it.

- **Requirement extraction** per listing: required / preferred / unspecified (wording unclear), with negation handling ("No degree required" is *not* a requirement). Covers years (digits, words, ranges, IT vs mechanical scope), certifications, degree (incl. "or equivalent"), clearance, driver's license, work authorization / sponsorship / citizenship, travel %, shifts, remote/hybrid/onsite, location, and pay written in the listing text.
- **Two separate scores**: `conv` (conventional: target title + demonstrated skills) and `adj` (adjacent/unconventional: transferable skills + adjacent titles). Learning/lab skills count far less and are labeled "not work experience".
- **Hard-requirement gate**: `PASS`, `REVIEW` (unknown facts or unclear wording), or `FAIL` (a required item you don't meet). Preferred items never block. Gate `REVIEW`/`FAIL` imports land in the new `needs_review` status. Shortlisting a `FAIL` job needs `--override-gate "reason"`, which is audited.
- **Evidence map**: every matched claim points to a profile `evidence` entry. `verified` only counts when a reference is filled in (portfolio entries need an http(s) URL); otherwise it is shown as `SELF_REPORTED` / downgraded. Nothing is auto-upgraded.
- **Pay source** is recorded: `listing_fields` (CSV columns) or `listing_text` (written in the description). Undisclosed stays "Not disclosed". `show` prints an annualized figure only as a labeled CALCULATION.
- **Dedup**: company + title + normalized URL (tracking params, www, trailing slash, case/whitespace ignored), plus a content hash for reposts under a different URL. Old v0.1/v0.2 rows still dedup.

### Fill in your facts (once)
Edit `profile.json` → `candidate_facts`. `null` means unknown and sends jobs to review. Only enter true facts. Then:

```sh
python job_hunter.py rescore
```

### Commands added
```sh
python job_hunter.py rescore                                  # re-evaluate after editing profile.json
python job_hunter.py status 3 shortlisted --override-gate "Recruiter confirmed clearance is sponsored"
python -m unittest discover -s tests -v                       # 19 tests, uses a temp folder, never your DB
```

## v0.4 — Milestone B: start button + ingestion

**One command:** `python job_hunter.py run` checks every enabled source in `sources.json`, ingests new jobs, and prints a phone-width dashboard (discovered, high match, unconventional, prepared, action needed, submitted).

Source types (implemented): `csv`, `json` (local files), `greenhouse`, `lever` (official public job-board APIs, no login). No LinkedIn/Indeed or sites without an official API.

- **Rate limits:** network sources are checked at most every `min_interval_minutes` (default 120). `--force` can never go below 10 minutes. 2 s delay between network sources. One request per source per run.
- **Filters (network only):** titles must match your profile/role keywords; senior/staff/lead/manager titles are dropped; location must be remote-US/Ohio/your commute cities. Local files are not filtered.
- **Metadata:** every job stores source, source type, external ID, source location, posted date, first seen, last seen. The `sources` table stores last checked, last OK, status and counts.
- **Cross-source dedup:** the same job from a CSV and an API is stored once; `last_seen_at` updates.
- **Pay:** API salary fields → `listing_fields`. A bare range like "$86,500 — $146,400" is accepted only if annual-sized, labeled "YEARLY period assumed".
- **Errors** in one source never stop the others; `last_ok_at` is kept.

```sh
python job_hunter.py run                 # start button
python job_hunter.py run --only gitlab   # one source
python job_hunter.py dashboard           # dashboard without checking sources
python job_hunter.py sources             # intervals + last checked
python job_hunter.py evidence            # full evidence references
python job_hunter.py show 4 --full       # whole description
```

To add a company: find its careers page. If the URL is `job-boards.greenhouse.io/<board>` or `jobs.lever.co/<board>`, add a source with that `board` and set `"enabled": true`.

## v0.5 — Milestone C: application drafts + Skill Gap Engine

Template-based (no AI model). **Nothing is ever sent.**

- `resume_facts.json` holds every resume bullet **verbatim** from your resume. Three variants select and reorder them: `it_support`, `qa_software`, `tech_security` (technical support / security trainee). Variants never add claims.
- `jh prepare N` (job must be `shortlisted`) writes `packets/NNNN-company-title/`:
  - `resume.md`: auto-chosen variant (override with `--variant qa_software`)
  - `packet.md`: listing summary, evidence map, pitch draft, unresolved questions, stretch/skill gaps with legal practice links, approval checklist
- Truthfulness rules (tested): the pitch claims only VERIFIED, non-lab skills; lab skills are labeled as labs; credentials you don't hold appear only under "Unresolved questions"; contact details appear only in `resume.md`.
- `jh approve N --note "reviewed"` records your approval plus a fingerprint of the packet files. `jh status N submitted --confirmation ID` now requires an approved packet that **hasn't changed since approval**, plus a real confirmation reference. You still submit on the employer's site yourself.
- `jh gaps` = Skill Gap Engine: skills/credentials your live jobs ask for that you can't back up yet, ranked by job count, with a free/legal resource each. Also lists lab-only skills employers want, so you can turn them into public proof. Saved to `reports/skill_gaps.md`.

**Your files are safe on updates:** editable files now ship in `defaults/` and are copied only if missing (`profile.json`, `sources.json`, `resume_facts.json`, `contact.local.json`). Unzipping a new version never overwrites them. `contact.local.json`, the database, packets and reports are in `.gitignore`.

```sh
jh status 2 shortlisted
jh prepare 2
less packets/0002-*/packet.md
jh approve 2 --note "reviewed"
# ...submit yourself on the employer site...
jh status 2 submitted --confirmation "THEIR-ID"
jh gaps
```

## v0.6 — BugHunter module (`jh bb ...`)

Shares JobHunter's database, profile evidence, Skill Gap Engine and audit log.

**Hard rule:** BugHunter downloads PUBLIC program listings and nothing else. It never sends a request to any program's targets: no scanning, fuzzing, crawling or exploit code (a test checks the module has no socket/subprocess code and only one download URL host). Active testing is a separate, manual step you take yourself after the scope checklist.

Sources: [bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data) (third-party mirror of HackerOne, Bugcrowd, Intigriti, YesWeHack public scopes) and [disclose.io diodb](https://github.com/disclose/diodb) (disclosure policies). Mirrors can be stale; the official program page is always the authority.

- **Scores (heuristic):** `beginner` (VDP/recognition, safe harbor, wildcard web scope, responsiveness; big payouts = more competition), `you` (your *demonstrated* skills vs asset types; Android/hardware/source code weigh most; lab skills get partial credit and are labeled LAB ONLY), `$` (bounty/max payout). Final is beginner-first.
- **Gate:** FAIL = closed/private. REVIEW = terms acceptance, 2FA, safe harbor unknown, scope only in policy text. PASS means "worth reading the policy", never "authorized to test".
- **Scope check** (offline, snapshot): out-of-scope always wins; wildcard apex flagged AMBIGUOUS; suffix tricks like `evilacme.test` rejected; CIDR supported.
- **Plan:** policy checklist, scope verification checklist, normal-user first session, skill gaps with legal labs, report skeleton. No tool commands.

```sh
jh bb sync                       # ~0.6 MB download for HackerOne, ~140 MB RAM peak; every 6 h max
jh bb list                       # beginner-first ranking
jh bb list --category android    # programs with Android app scope (your strength)
jh bb list --vdp                 # recognition/VDP only
jh bb show 11
jh bb plan 11                    # writes bugbounty/plans/0011-*.md
jh bb scope 11 shop.example.com  # offline check vs snapshot; not permission
jh bb mark 11 watching|studying|skipped
jh bb gaps                       # what to learn for the best-fit programs
```
