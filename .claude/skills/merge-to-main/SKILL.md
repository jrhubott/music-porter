---
name: merge-to-main
description: Merge dev into main with version bump, tagging, and release workflow
model: opus
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Grep, Glob, AskUserQuestion, Skill
---

Merge the dev branch into main following the project's 3-tier version workflow.

## Steps

1. **Verify state**
   - If not on the `dev` branch, automatically switch to it: `git checkout dev`
   - Run `git status` to ensure the working tree is clean — abort if there are uncommitted changes
   - Run `git log main..dev --oneline` to summarize what will be merged

2. **Sync with remote**
   - Run `git fetch origin` to get latest remote state
   - Skip this step if no `origin` remote exists (local-only repo)
   - Check if local main is behind remote: `git rev-list main..origin/main --count`
   - If behind, update local main: `git checkout main && git pull origin main && git checkout dev`
   - If diverged (local main is both ahead and behind origin/main), warn the user and abort — manual resolution needed
   - Check if local dev is behind remote: `git rev-list dev..origin/dev --count`
   - If behind, update local dev: `git pull origin dev`

3. **Determine version bump**
   - Read the current VERSION from `porter_core.py` (line 50)
   - Extract the base version (the part before the `-dev` suffix — strip any `+hash` build metadata too)
   - Analyze the commits on dev since main to determine the nature of changes
   - Ask the user which version bump to apply:
     - **PATCH** (e.g. 1.5.1 -> 1.5.2): Bug fixes, docs, minor improvements
     - **MINOR** (e.g. 1.5.1 -> 1.6.0): New features, non-breaking changes
     - **MAJOR** (e.g. 1.5.1 -> 2.0.0): Breaking changes, major refactors
   - Suggest the most appropriate level based on the changes

4. **Check README future features**
   - Search the README "Future Features" section for items that match the changes being merged
   - If a match is found, strikethrough the item with `~~text~~` and add "*(implemented in vX.Y.Z)*" — keep original numbering intact
   - Only ask the user if a plausible match exists; skip this step silently if no items relate to the changes

5. **Validate SRS requirements**
   - Scan ALL `.md` files in the `SRS/` directory (dev may accumulate multiple features)
   - For each SRS file, check for unchecked checkboxes (`[ ]` in the Tested column)
   - If ANY requirements are unchecked in ANY SRS file, **abort the merge** — list all incomplete requirements across all files and tell the user they must be completed before merging
   - If all requirements are checked (`[x]`) across all SRS files, proceed to the next step
   - If no SRS files exist, skip this step silently

6. **Add unfinished work to README**
   - Review the commits and diffs between main and dev for TODOs, FIXMEs, partial implementations, known limitations, or follow-up work that was deferred
   - Also check for any comments in the code mentioning future improvements
   - Also check `todos.md` (via `/todo list`) for active items that represent future work — these may belong in the README "Future Features" list even if they weren't completed
   - If any unfinished items are found (from code, diffs, or todos.md), ask the user which (if any) should be added to the README "Future Features" list
   - Append new items to the appropriate priority section (High / Medium / Low), continuing the existing numbering
   - Keep descriptions concise and consistent with the existing list style: `**Bold title** - Description`

7. **Update todos.md**
   - Use `/todo list` (via the Skill tool) to view current todos
   - Identify any active todos that match the work completed in this release
   - For each matching active todo, use `/todo complete` (via the Skill tool) with the todo text to mark it done
   - If no todos.md exists or no active todos match, skip this step silently
   - Do NOT ask the user — complete matching todos automatically as part of the merge

8. **Generate release notes**
   - Review all commits since the previous version tag (`git log $(git describe --tags --abbrev=0 main)..dev --oneline`)
   - Prepend a new entry to the top of `release-notes.txt` with format: `Version X.Y.Z (YYYY-MM-DD):` header followed by bullet points (`• description`)
   - Stage `release-notes.txt`

9. **Check iOS app version**
   - Run `git diff $(git describe --tags --abbrev=0 main)..dev --name-only -- ios/` to detect iOS file changes since the last release
   - If no iOS files changed → skip this step silently
   - If iOS files changed:
     - Read the current `appVersion` from `ios/MusicPorter/MusicPorter/MusicPorterApp.swift`
     - Show the user the current iOS version and a summary of iOS changes
     - Ask what the new iOS version should be (suggest PATCH bump as default)
     - Update the `appVersion` constant in `MusicPorterApp.swift`
     - Include the iOS version bump as a bullet point in the release notes generated in step 8 (e.g., `• iOS app version bumped to X.Y.Z`)

10. **Update version and commit on dev**
   - Edit `porter_core.py` line 50 to set `VERSION = "X.Y.Z"` (clean version, no `-dev` suffix)
   - Stage the version change (and README, release-notes.txt, MusicPorterApp.swift if modified)
   - Commit on dev with message: `Update version to X.Y.Z for merge to main`
   - Do NOT include Co-Authored-By lines
   - **Important:** This commit must happen BEFORE checking out main, otherwise uncommitted changes will block the checkout

11. **Merge**
    - `git checkout main`
    - `git merge dev --no-ff` (preserve branch history in merge commit)
    - If merge conflicts occur:
      - List the conflicted files with `git diff --name-only --diff-filter=U`
      - Show the conflict markers with `git diff` so the user can see both sides
      - Ask the user for guidance on how to resolve each conflict
      - After resolution, stage resolved files and complete the merge commit
      - Do NOT include Co-Authored-By lines in the merge commit
    - If the user wants to abandon the merge, run `git merge --abort` and stop

12. **Verify merge**
    - Verify working tree is clean: `git status`
    - Verify dev commits are present: `git log --oneline -10` should include the dev branch commits
    - Verify VERSION matches the expected clean `X.Y.Z`: read line 50 of `porter_core.py`
    - If any check fails, warn the user and ask whether to proceed with tagging or abort

13. **Update SRS metadata**
    - For each SRS file found in step 5, update its status line from "In Progress" to "Complete" and add `**Implemented in:** vX.Y.Z`
    - Stage and commit: `Mark SRS complete for vX.Y.Z`
    - Do NOT include Co-Authored-By lines
    - SRS files remain in `SRS/` permanently — do NOT archive or delete them

14. **Tag the release**
    - `git tag vX.Y.Z`

15. **Set next dev version**
    - `git checkout dev && git merge main` (sync dev with main)
    - Ask the user for the next anticipated version (suggest next PATCH as default, e.g. if releasing 2.30.0, suggest 2.31.0)
    - Edit `porter_core.py` line 50 to set `VERSION = "X.Y.Z-dev"` (with `-dev` suffix)
    - Stage and commit: `Set next dev version to X.Y.Z-dev`
    - Do NOT include Co-Authored-By lines

16. **Clean up feature branches**
    - List branches already merged into dev: `git branch --merged dev` (exclude main and dev from the list)
    - If there are merged branches, show the list and ask the user which to delete
    - For each branch the user wants to delete, run `git branch -d <branch-name>`
    - If no merged branches exist, skip this step silently

17. **Push to remote**
    - Ask the user if they want to push to origin now
    - If yes, run `git push origin main dev --tags`
    - If push fails (e.g. rejected), warn the user and show the error — do NOT force push

18. **Report**
    - Show the final `git log --oneline -5` on main to confirm
    - Show the tag: `git tag -l 'vX.Y.Z'`
    - Show the current dev version: read line 50 of `porter_core.py`
