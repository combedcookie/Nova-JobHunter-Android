# NOVA JobHunter pre-push candidate

## Automated tests passed
- `node test.cjs`
- `node test-interactions.cjs` (25 inline event patterns, native bridge method existence, all seven screens, redraw-sensitive location handling, application and bounty flows, audit and settings dispatch)

## Fixes
- Capture location before redrawing Jobs form.
- Gracefully handle unavailable Android bridge in settings and external-link actions.
- Reject malformed non-array saved data instead of breaking rendering.
- Display a minimal startup error if initial rendering throws.
- CI executes both test suites before Gradle build.

## NOT verified — do not label as fully functional
- Actual Android WebView startup and screen display (previous blank screen not reproduced).
- APK compilation (project ZIP lacks root Gradle wrapper/build files).
- Live Remotive/Adzuna/USAJOBS/HackerOne responses, API credentials and encrypted Android Keystore.
- Real Android external links, audit networking, saved state across app restarts.
- Stable release signing, upgrade compatibility and custom launcher icon.

## Installation
Unzip into a separate directory, compare changes, back up current project, and merge app/src/main/assets/index.html, test-interactions.cjs and .github/workflows/build-apk.yml. Existing MainActivity.java retained. Never overwrite keys or commit secrets.
