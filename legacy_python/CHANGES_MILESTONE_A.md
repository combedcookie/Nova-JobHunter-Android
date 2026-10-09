# Milestone A — audit + changes

## v0.1/v0.2 bugs found (reproduced before changing anything)
1. `status N submitted --confirmation "   "` was accepted (whitespace-only proof). Fixed: stripped, min 4 chars.
2. Negation ignored: "Not a cybersecurity role" counted as a cybersecurity match. Fixed (clause + 3-word window).
3. Title matching used substrings: `qa` matched "Squad", "Aquarium". Fixed: word boundaries.
4. Caution phrases were exact substrings: "CompTIA A+ is required. Five years" was NOT flagged. Replaced by the extractor.
5. Dedup broke on `?ref=`/`utm_` params, `www.`, trailing slash, reposts. Fixed (normalized URL + content hash; legacy hash still checked).
6. `notifications.jsonl` was written before the DB commit, so a failed commit left phantom events. Fixed: flushed after commit.
7. Learning/lab skills raised the *conventional* score (+3 each) as if they were experience. Now +2 and labeled lab-only.
8. Paths were import-time constants, so tests couldn't isolate the DB. Added `JOBHUNTER_HOME`.
9. Undisclosed pay stored currency `USD` anyway. Now NULL.
10. No `needs_review` state; unknowns were invisible. Added.

## Still fragile (known, honest)
- Regex extraction: unusual wording will slip through. `show` prints the source snippet for every extracted item so you can check.
- "unspecified" items (no required/preferred word) are treated as probable; 2+ probable misses become FAIL.
- Location check is only a "check commute" note; no distance math.
- Scores are heuristics, not probabilities.
