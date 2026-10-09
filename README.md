# NOVA Board — Android preview

A real Android WebView application with an offline cream-and-copper interface inspired by the supplied mockup. Built for GitHub Actions without Android Studio.

## Features working in this preview
- Tabs: Overview, Jobs, BugHunter, Applications, Learn.
- Displays **fictional** job examples with advertised salary and illustrative scores.
- Saves tracked applications, manually updates status, and asks for confirmation before marking submitted.
- Saves manual bug-bounty program notes. No active security testing.
- Local WebView storage persists on device.

## Not yet integrated
The `legacy_python/` folder contains the user's v0.6 Python source **as reference only**. This APK does **not** execute the Python modules. No live job feeds, AI scoring, email, browser automation, bounty sync, or automatic applications are connected. Those require subsequent development and permission checks.

## Build
Push all project files to the repository. GitHub Actions > Build NOVA APK > Run workflow. Download `NOVA-Board-debug-apk` artifact and extract `app-debug.apk` to install.

## Phone / Termux upload
From the existing Git repository directory, unzip this package **into the directory** (not a nested folder), then:
```
git add .
git commit -m "Add NOVA Board Android preview"
git push origin main
```
Never commit API tokens, SMTP credentials, private personal data, or browser session cookies. The `.gitignore` excludes some sensitive filenames but is not a complete secret scanner.
