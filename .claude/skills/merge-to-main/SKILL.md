---
name: merge-to-main
description: Merge dev into main with version bump, tagging, and release workflow
model: opus
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Grep, Glob, AskUserQuestion
---

Merge dev into main following the 3-tier version workflow.

## Steps

1. **Verify and sync**
   - Switch to dev if not already on it
   - Abort if working tree is not clean
   - `git fetch origin` (skip if no remote)
   - Update local main if behind remote (abort if diverged)
   - Update local dev if behind remote
   - Show `git log main..dev --oneline`

2. **Determine versions**
   - Read VERSION from `porter_core.py` line 50, extract base version (strip `-dev+hash`)
   - Check for iOS changes: `git diff $(git describe --tags --abbrev=0 main)..dev --name-only -- ios/`
   - **Single prompt** asking: version bump type (PATCH/MINOR/MAJOR with suggestion based on commits), and if iOS files changed, also ask for new iOS version (suggest PATCH bump of current `appVersion` from `MusicPorterApp.swift`)

3. **Prepare release on dev**
   - **SRS gate:** Scan all `SRS/*.md` for unchecked `[ ]` — abort listing all incomplete items if any found
   - **README:** Silently strikethrough any Future Features matching this release, adding "*(implemented in vX.Y.Z)*"
   - **Release notes:** Prepend entry to `release-notes.txt` — `Version X.Y.Z (YYYY-MM-DD):` with bullet points from commits since last tag
   - **iOS:** If applicable, update `appVersion` in `MusicPorterApp.swift` and add bullet to release notes
   - **Version commit:** Set `VERSION = "X.Y.Z"` in `porter_core.py`, stage all changes, commit: `Update version to X.Y.Z for merge to main`

4. **Merge to main**
   - `git checkout main && git merge dev --no-ff`
   - On conflict: show conflicts and ask user for resolution guidance (abort if requested)
   - Verify: clean tree, VERSION matches, dev commits present in log

5. **Tag and set next dev version**
   - `git tag vX.Y.Z`
   - `git checkout dev && git merge main`
   - Auto-set next version: increment only the PATCH component (e.g., 2.34.0 → 2.34.1-dev, NOT 2.35.0-dev), set `VERSION = "X.Y.Z-dev"` (no hash — merge-to-dev adds it)
   - Commit: `Set next dev version to X.Y.Z-dev`

6. **Push, clean up, report**
   - `git push origin main dev --tags` (warn on failure — never force push)
   - Auto-delete branches merged into dev (`git branch --merged dev`, excluding main/dev)
   - Show final `git log main --oneline -5`, tag, and current dev version
