---
name: merge-to-main
description: Merge the current feature branch into main with version bump and git tag
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Grep, Glob, AskUserQuestion
---

Merge the current feature branch into main following the project's version workflow.

## Steps

1. **Verify state**
   - Confirm we are on a feature branch (not main)
   - Run `git status` to ensure the working tree is clean — abort if there are uncommitted changes
   - Run `git log main..HEAD --oneline` to summarize what will be merged

2. **Determine version bump**
   - Read the current VERSION from `apple-to-ride-command` (line 68)
   - Extract the base version (the part before the `-branch-name` suffix)
   - Analyze the commits on this branch to determine the nature of changes
   - Ask the user which version bump to apply:
     - **PATCH** (e.g. 1.5.1 -> 1.5.2): Bug fixes, docs, minor improvements
     - **MINOR** (e.g. 1.5.1 -> 1.6.0): New features, non-breaking changes
     - **MAJOR** (e.g. 1.5.1 -> 2.0.0): Breaking changes, major refactors
   - Suggest the most appropriate level based on the changes

3. **Check README future features**
   - Search the README "Future Features" section for items that match this branch's changes
   - If a match is found, strikethrough the item with `~~text~~` and add "*(implemented in vX.Y.Z)*" — keep original numbering intact
   - Only ask the user if a plausible match exists; skip this step silently if no items relate to the branch

4. **Add unfinished work to README**
   - Review the branch's commits and diffs for TODOs, FIXMEs, partial implementations, known limitations, or follow-up work that was deferred
   - Also check for any comments in the code mentioning future improvements related to this branch's changes
   - If any are found, ask the user which (if any) should be added to the README "Future Features" list
   - Append new items to the appropriate priority section (High / Medium / Low), continuing the existing numbering
   - Keep descriptions concise and consistent with the existing list style: `**Bold title** - Description`

5. **Update version and commit on feature branch**
   - Edit `apple-to-ride-command` to set `VERSION = "X.Y.Z"` (clean version, no branch suffix)
   - Stage the version change (and README if modified)
   - Commit on the feature branch with message: `Update version to X.Y.Z for merge to main`
   - Do NOT include Co-Authored-By lines
   - **Important:** This commit must happen BEFORE checking out main, otherwise uncommitted changes will block the checkout

6. **Merge**
   - `git checkout main`
   - `git merge <branch-name>`

7. **Tag the release**
   - `git tag vX.Y.Z`

8. **Clean up**
   - Ask the user if they want to delete the feature branch
   - If yes, run `git branch -d <branch-name>`

9. **Report**
   - Show the final `git log --oneline -5` so the user can verify
   - Show the tag: `git tag -l 'vX.Y.Z'`
   - Remind the user to `git push origin main --tags` when ready
