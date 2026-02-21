---
name: merge-to-main
description: Merge the current feature branch into main with version bump and git tag
model: opus
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Grep, Glob, AskUserQuestion, Skill
---

Merge the current feature branch into main following the project's version workflow.

## Steps

1. **Verify state**
   - Confirm we are on a feature branch (not main)
   - Run `git status` to ensure the working tree is clean — abort if there are uncommitted changes
   - Run `git log main..HEAD --oneline` to summarize what will be merged

2. **Sync with remote main**
   - Run `git fetch origin` to get latest remote state
   - Skip this step if no `origin` remote exists (local-only repo)
   - Check if local main is behind remote: `git rev-list main..origin/main --count`
   - If behind, update local main: `git checkout main && git pull origin main && git checkout -` (return to feature branch)
   - If diverged (local main is both ahead and behind origin/main), warn the user and abort — manual resolution needed

3. **Determine version bump**
   - Read the current VERSION from `music-porter` (line 68)
   - Extract the base version (the part before the `-branch-name` suffix)
   - Analyze the commits on this branch to determine the nature of changes
   - Ask the user which version bump to apply:
     - **PATCH** (e.g. 1.5.1 -> 1.5.2): Bug fixes, docs, minor improvements
     - **MINOR** (e.g. 1.5.1 -> 1.6.0): New features, non-breaking changes
     - **MAJOR** (e.g. 1.5.1 -> 2.0.0): Breaking changes, major refactors
   - Suggest the most appropriate level based on the changes

4. **Check README future features**
   - Search the README "Future Features" section for items that match this branch's changes
   - If a match is found, strikethrough the item with `~~text~~` and add "*(implemented in vX.Y.Z)*" — keep original numbering intact
   - Only ask the user if a plausible match exists; skip this step silently if no items relate to the branch

5. **Validate SRS requirements**
   - Check the `SRS/` directory for any `.md` files related to this branch's feature
   - If an SRS file exists, scan for unchecked checkboxes (`- [ ]`)
   - If ANY requirements are unchecked, **abort the merge** — list the incomplete requirements and tell the user they must be completed before merging
   - If all requirements are checked (`- [x]`), proceed to the next step
   - If no SRS file exists for this branch, skip this step silently

5b. **Add unfinished work to README**
   - Review the branch's commits and diffs for TODOs, FIXMEs, partial implementations, known limitations, or follow-up work that was deferred
   - Also check for any comments in the code mentioning future improvements related to this branch's changes
   - Also check `todos.md` (via `/todo list`) for active items that represent future work related to this branch — these may belong in the README "Future Features" list even if they weren't completed
   - If any unfinished items are found (from code, diffs, or todos.md), ask the user which (if any) should be added to the README "Future Features" list
   - Append new items to the appropriate priority section (High / Medium / Low), continuing the existing numbering
   - Keep descriptions concise and consistent with the existing list style: `**Bold title** - Description`

5c. **Update todos.md**
   - Use `/todo list` (via the Skill tool) to view current todos
   - Identify any active todos that match the work completed on this branch
   - For each matching active todo, use `/todo complete` (via the Skill tool) with the todo text to mark it done
   - If no todos.md exists or no active todos match, skip this step silently
   - Do NOT ask the user — complete matching todos automatically as part of the merge

6. **Update version and commit on feature branch**
   - Edit `music-porter` to set `VERSION = "X.Y.Z"` (clean version, no branch suffix)
   - Stage the version change (and README if modified)
   - Commit on the feature branch with message: `Update version to X.Y.Z for merge to main`
   - Do NOT include Co-Authored-By lines
   - **Important:** This commit must happen BEFORE checking out main, otherwise uncommitted changes will block the checkout

7. **Merge**
   - `git checkout main`
   - `git merge <branch-name> --no-ff` (preserve branch history in merge commit)
   - If merge conflicts occur:
     - List the conflicted files with `git diff --name-only --diff-filter=U`
     - Show the conflict markers with `git diff` so the user can see both sides
     - Ask the user for guidance on how to resolve each conflict
     - After resolution, stage resolved files and complete the merge commit
     - Do NOT include Co-Authored-By lines in the merge commit
   - If the user wants to abandon the merge, run `git merge --abort` and stop

8. **Verify merge**
   - Verify working tree is clean: `git status`
   - Verify branch commits are present: `git log --oneline -10` should include the feature branch commits
   - Verify VERSION matches the expected clean `X.Y.Z`: read line 68 of `music-porter`
   - If any check fails, warn the user and ask whether to proceed with tagging or abort

9. **Tag the release**
   - `git tag vX.Y.Z`

10. **Archive SRS document**
    - If an SRS file was found in step 5, archive it into `SRS.md` (root of repo)
    - **Read `SRS.md` first** to understand its existing format and structure before making changes
    - If `SRS.md` does not exist, create it with a `# Completed SRS Documents` heading
    - If `SRS.md` already exists, match its existing format:
      - Use the same heading style, separator style (`---`), and metadata fields as existing entries
      - Add an `**Implemented in:** vX.Y.Z` metadata line to the new entry's header block
      - Append the new entry after the last existing entry, separated by `---`
    - Delete the individual SRS file from the `SRS/` directory
    - If the `SRS/` directory is now empty, delete it
    - Stage and commit: `Archive SRS: <feature-name> into SRS.md`
    - Do NOT include Co-Authored-By lines

11. **Clean up**
    - Ask the user if they want to delete the feature branch
    - If yes, run `git branch -d <branch-name>`

12. **Report**
    - Show the final `git log --oneline -5` so the user can verify
    - Show the tag: `git tag -l 'vX.Y.Z'`
    - Remind the user to `git push origin main --tags` when ready
