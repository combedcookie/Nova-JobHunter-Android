# BugHunter plan: DuckDuckGo (hackerone)

PLANNING DOCUMENT ONLY. NOVA has not contacted any target and never will.
Active testing is a separate manual step you take only after the checklist below is done.

## Program
- Official page (the authority): https://hackerone.com/duckduckgo
- Policy: https://hackerone.com/duckduckgo
- Type: VDP / recognition
- Safe harbor (per data): not stated
- Scores (heuristic): beginner 70 | your strengths 70 | reward 0 | gate REVIEW
- Scope snapshot: 2026-10-09T23:00 via third-party mirror; may be stale

## Why it scored this way
- VDP / recognition program: less competition, good first reports
- 1 wildcard scope(s): more surface to learn on
- Your verified strengths apply: web: burp suite, api testing (LAB ONLY); android: android, kotlin, jetpack compose, android studio; source_code: python, kotlin, git
- ? Safe harbor not confirmed in data: check the policy

## In-scope assets (snapshot)
- [web] *.duckduckgo.com
- [android] com.duckduckgo.mobile.android
- [ios] com.duckduckgo.mobile.ios
- [source_code] https://github.com/duckduckgo/duckduckgo-privacy-extension

## Out of scope (snapshot): never touch these
- none listed in data: read the policy; absence here does not mean allowed

## Scope verification checklist (do ALL before any testing)
- [ ] Opened the official program page and read the full policy today
- [ ] Target is listed in scope on the official page (not only in this snapshot)
- [ ] Ran `jh bb scope 353 <target>` and it says LISTED_IN_SCOPE
- [ ] Noted rules: rate limits, banned techniques, test-account rules, required headers
- [ ] Program allows the testing type you plan (e.g. no automated scanning if banned)
- [ ] Using only your own test accounts and data; never other users
- [ ] Know how to report and the disclosure rules

## First session: learn the product as a normal user
- Use the in-scope app/site the way a normal customer would. No tools, no unusual traffic.
- Write down features, roles, and where login, permissions, and payments happen.
- Read the program's public disclosed reports (if any) to see what they accept.
- Pick ONE bug class you have practiced in a legal lab, and plan how you would test it within the rules.

## Skill gaps and legal practice first
- web: HTTP, auth/session and access-control testing (lab basics only so far)
  - PortSwigger Web Security Academy: https://portswigger.net/web-security
  - OWASP Web Security Testing Guide: https://owasp.org/www-project-web-security-testing-guide/
  - Hacker101 (free, HackerOne): https://www.hacker101.com/
- android: Android app security testing (storage, IPC, network) (you have the dev base; learn the security side)
  - OWASP MASTG (mobile testing guide): https://mas.owasp.org/MASTG/
- ios: iOS app security testing (needs Apple hardware)
  - OWASP MASTG (mobile testing guide): https://mas.owasp.org/MASTG/
- source_code: Secure code review (you have the dev base; learn the security side)
  - OWASP Code Review Guide: https://owasp.org/www-project-code-review-guide/

## Report skeleton (fill in only with what you actually observed)
- Title:
- Asset (exactly as listed in scope):
- Steps to reproduce:
- Impact:
- Evidence (your own account/data only):
- Date/time and your test account:
