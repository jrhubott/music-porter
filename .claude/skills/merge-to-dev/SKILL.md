---
name: merge-to-dev
description: Merge the current feature branch into dev — fast and fully automatic
model: opus
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Grep, Glob
---

Merge the current feature branch into dev. This is fast and fully automatic — no user prompts, no questions asked.

## Steps

1. **Verify state**
   - Confirm we are on a feature or bugfix branch (not dev, not main)
   - Run `git status` to ensure the working tree is clean — abort if there are uncommitted changes
   - Run `git log dev..HEAD --oneline` to summarize what will be merged

2. **Sync with remote**
   - Run `git fetch origin` to get latest remote state
   - Skip this step if no `origin` remote exists (local-only repo)
   - Check if local dev is behind remote: `git rev-list dev..origin/dev --count`
   - If behind, update local dev: `git checkout dev && git pull origin dev && git checkout -` (return to feature branch)
   - If diverged (local dev is both ahead and behind origin/dev), abort — report the divergence and stop

3. **Merge into dev**
   - `git checkout dev`
   - `git merge <branch-name> --no-ff` (preserve branch history in merge commit)
   - Do NOT include Co-Authored-By lines in the merge commit
   - If merge conflicts occur:
     - Run `git merge --abort`
     - Run `git checkout <branch-name>` (return to the original feature branch)
     - List the conflicted files and report them
     - Stop — do NOT attempt to resolve conflicts

4. **Restore dev version suffix**
   - Read VERSION from `porter_core.py` line 50
   - Extract the base version (the part before the `-branch-name` suffix)
   - Edit `porter_core.py` line 50 to set `VERSION = "X.Y.Z-dev"` (replace the branch-name suffix with `-dev`)
   - Stage and commit: `Restore dev version suffix`
   - Do NOT include Co-Authored-By lines

5. **Push to remote**
   - Run `git push origin dev`
   - If push fails, warn and stop — do NOT force push

6. **Return to feature branch**
   - `git checkout <branch-name>` (return to the original feature branch)
   - Do NOT delete the feature branch — cleanup happens at merge-to-main time

7. **Report**
   - Show `git log dev --oneline -5` to confirm the merge
   - Report success

## What this skill does NOT do

- No version bump (only restores the `-dev` suffix on dev)
- No SRS validation (deferred to merge-to-main)
- No README checks
- No linting enforcement
- No tagging
- No user prompts or questions — everything is automatic
