---
name: merge-to-dev
description: Merge the current feature branch into dev — fast and fully automatic
model: opus
disable-model-invocation: true
allowed-tools: Bash, Read, Edit, Grep, Glob
---

Merge the current feature branch into dev. Fully automatic — no user prompts.

## Steps

1. **Verify and sync**
   - Confirm on a feature/bugfix branch (not dev, not main) — abort otherwise
   - Abort if working tree is not clean (`git status`)
   - Show `git log dev..HEAD --oneline` to summarize what will be merged
   - `git fetch origin` (skip if no remote)
   - If local dev is behind remote, update it: `git checkout dev && git pull origin dev && git checkout -`
   - If dev has diverged from remote, abort and report

2. **Merge into dev**
   - `git checkout dev`
   - `git merge <branch> --no-ff`
   - On conflict: `git merge --abort`, return to feature branch, list conflicts, stop

3. **Restore dev version**
   - Read VERSION from `porter_core.py` line 50
   - Get short merge commit hash: `git rev-parse --short HEAD`
   - Set `VERSION = "X.Y.Z-dev+<hash>"` (base version from before branch suffix)
   - Commit: `Set dev version to X.Y.Z-dev+<hash>`

4. **Push and report**
   - `git push origin dev` (warn and stop on failure — never force push)
   - `git checkout <branch>` (return to feature branch)
   - Show `git log dev --oneline -5` to confirm
