# SRS: Release Workflow (`cut-release.py`)

Requirements document for `build/cut-release.py`, the standalone release orchestration script for music-porter.

---

## Format Preamble

### Column Schema

| Column | Meaning |
|--------|---------|
| **ID** | Globally unique requirement identifier within this document. Format: `<section>.<sequence>` (e.g. `1.1`, `2.3`). |
| **Interactive** | Status for a developer running the script at an interactive terminal with a TTY, ANSI color, and access to `$EDITOR`. |
| **Automated** | Status for a CI/CD pipeline: no TTY, no human, no editor. Exit codes consumed by the pipeline. |
| **Scripted** | Status for semi-automated use (cron, deploy hook, manual trigger via wrapper script): may have a TTY but prompts are pre-answered via flags. |

### Status Values

| Symbol | Meaning |
|--------|---------|
| `[x]` | Implemented and verified. |
| `[ ]` | Not yet implemented. |
| `N/A` | Explicitly decided not applicable for this execution context. |

### Roles Used in Requirements

| Role | Who they are |
|------|-------------|
| **developer** | A human at a terminal, actively running the script during normal release work. |
| **CI operator** | A pipeline process (GitHub Actions, Jenkins, etc.) invoking the script non-interactively. |
| **release engineer** | A human or automation that has pre-scripted answers for all prompts and needs consistent, repeatable releases. |

### How to Add New Requirements

1. Determine the section (1.0–12.0) the requirement belongs to.
2. Assign the next available sequence number within that section (e.g. if the last in section 4 is `4.3`, the new one is `4.4`).
3. Write the requirement as: *"As a [role], I can [action] so that [benefit]. Acceptance: [measurable criteria]."*
4. Set `[ ]` in all three context columns unless the requirement is truly N/A for a context, in which case use `N/A`.
5. Mark `[x]` only after the feature is implemented and manually verified in that context.

---

## 1.0 Pre-flight Verification

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 1.1 | [x] | [x] | [x] | As a developer, I can run the script from any subdirectory of the project so that I don't have to `cd` to the root first. Acceptance: `verify_project_root()` walks up the directory tree until it finds `porter_core.py` and `.git/`; exits with a clear error if not found. |
| 1.2 | [x] | [x] | [x] | As a developer, I can have the script automatically switch to the `dev` branch if I'm on another branch so that I don't accidentally cut the release from the wrong branch. Acceptance: if `HEAD` is not `dev`, the script runs `git checkout dev` before any other operations. |
| 1.3 | [x] | [x] | [x] | As a CI operator, I can have all validation of required flags happen before any git operations run so that a misconfigured invocation fails fast without leaving the repo in a partially-modified state. Acceptance: `--non-interactive` + missing `--bump` exits with a clear error before `step1_verify_and_sync()` is called. |

---

## 2.0 Dirty Tree Recovery

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 2.1 | [x] | [x] | [x] | As a developer, I can be offered three options when the working tree is dirty (stash and continue, clean up and retry, or abort) so that I can recover without restarting the script. Acceptance: dirty tree check loops until the tree is clean or stashed; a numeric menu is presented in interactive mode. |
| 2.2 | [x] | [x] | [x] | As a release engineer, I can pass `--auto-stash` so that the script automatically stashes any dirty changes and pops the stash at the end, enabling unattended runs without pre-cleaning. Acceptance: `git stash push -u` is called if the tree is dirty when `--auto-stash` is set; the stash is popped in a `try/finally` block regardless of success or failure. |
| 2.3 | [x] | [x] | [x] | As a CI operator, I can run with `--non-interactive --auto-stash` so that a dirty tree is handled automatically without prompting. Acceptance: in `--non-interactive` mode, a dirty tree without `--auto-stash` prints a clear error and exits non-zero; with `--auto-stash` it stashes silently. |

---

## 3.0 Remote Sync and Divergence

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 3.1 | [x] | [x] | [x] | As a developer, I can have the script automatically fast-forward `main` and `dev` from `origin` when they are behind so that I don't accidentally release from a stale local state. Acceptance: `git fetch origin` is run before sync; `git fetch origin branch:branch` fast-forwards any branch that is behind its remote counterpart. |
| 3.2 | [x] | [x] | [x] | As a developer, I can be shown a recovery menu when `dev` has truly diverged from `origin/dev` (neither is an ancestor of the other) so that I can make an informed decision before the release proceeds. Acceptance: the menu shows local/remote commit counts, offers to show diverging commits (then abort), abort, or continue with explicit YES confirmation; `--non-interactive` always exits immediately on diverge. |
| 3.3 | [x] | [x] | [x] | As a developer, I can choose option 1 in the diverge menu to see all commits that differ between local and remote so that I understand the scope of the divergence before deciding how to proceed. Acceptance: `git log origin/dev..dev --oneline` and `git log dev..origin/dev --oneline` are both printed; the script exits after displaying them. |

---

## 4.0 Version Bumping

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 4.1 | [x] | [x] | [x] | As a developer, I can choose PATCH, MINOR, or MAJOR for the server version bump via an interactive numbered menu so that semantic versioning is applied correctly. Acceptance: menu shows current base version; input "1"/"2"/"3" or "patch"/"minor"/"major" selects the bump type; defaults to PATCH on Enter. |
| 4.2 | [x] | [x] | [x] | As a release engineer, I can pass `--bump {patch,minor,major}` so that the server version bump type is pre-answered without a prompt. Acceptance: `--bump patch` produces a PATCH bump; `--bump minor` a MINOR bump; `--bump major` a MAJOR bump. `--non-interactive` requires `--bump`. |
| 4.3 | [x] | [x] | [x] | As a developer, I can be prompted for a new iOS appVersion only when `ios/` changes are detected since the last tag so that iOS version bumps are not forgotten when iOS code changes. Acceptance: `git diff <last_tag>..dev --name-only -- ios/` determines if iOS changed; the suggested version is a PATCH bump of the current `appVersion`. |
| 4.4 | [x] | [x] | [x] | As a release engineer, I can pass `--ios-version X.Y.Z` to pre-answer the iOS version or `--no-ios-bump` to suppress it so that iOS version decisions are scriptable. Acceptance: `--no-ios-bump` suppresses bump even when iOS changes are detected (with a warning); `--ios-version` applies the given version string; `--non-interactive` exits with a clear error if iOS changes are detected and neither flag is provided. |
| 4.5 | [x] | [x] | [x] | As a developer, I can be prompted for a new sync-client VERSION only when `sync-client/` changes are detected since the last tag so that sync-client version bumps are not forgotten. Acceptance: same detection and suggestion logic as iOS (4.3), applied to `sync-client/` and `constants.ts`. |
| 4.6 | [x] | [x] | [x] | As a release engineer, I can pass `--sync-version X.Y.Z` or `--no-sync-bump` to pre-answer the sync-client version decision. Acceptance: mirrors 4.4 for the sync-client. |

---

## 5.0 Release Notes

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 5.1 | [x] | [x] | [x] | As a developer, I can see an auto-generated draft of release notes built from commits since the last tag so that I have a useful starting point before editing. Acceptance: `git log <last_tag>..dev --oneline --no-merges` is filtered to exclude housekeeping commits (set next dev version, update version to, merge branch, merge remote-tracking); formatted as `• <message>` bullets under a `Version X.Y.Z (YYYY-MM-DD):` header. |
| 5.2 | [x] | N/A | [x] | As a developer, I can be offered the option to open the draft in `$EDITOR` to refine it before it is committed so that I can correct wording or add context. Acceptance: a Y/n prompt asks if the user wants to edit; if yes, the draft is written to a temp file, `$EDITOR` (falling back to `vi`) is launched, and the edited text is used. `--no-editor` skips this prompt. |
| 5.3 | [x] | [x] | [x] | As a release engineer, I can pass `--release-notes-from FILE` to supply a pre-written release notes file so that the auto-generation and editor steps are bypassed entirely. Acceptance: the file's contents are used verbatim as the release notes entry; the script aborts with a clear error if the file does not exist. |
| 5.4 | [x] | [x] | [x] | As a release engineer, I can pass `--release-notes-append TEXT` (repeatable) to add extra bullet points to the auto-generated draft so that CI-aware additions (e.g. build numbers, migration notes) can be injected without a full file override. Acceptance: each `--release-notes-append` value is prepended with `• ` and appended to the draft before the editor step. |
| 5.5 | [x] | [x] | [x] | As a developer, I can see iOS and sync-client version bumps automatically appended as bullets to the release notes draft so that component updates are always documented. Acceptance: if `ios_new` or `sync_new` is non-empty, `• iOS companion app updated to vX.Y.Z` / `• Sync client updated to vX.Y.Z` are appended before the editor step. |

---

## 6.0 SRS Gate

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 6.1 | [x] | [x] | [x] | As a developer, I can see a list of all `SRS/*.md` rows that still have `[ ]` in any client column when the SRS gate fails so that I know exactly what is incomplete before deciding whether to proceed. Acceptance: each incomplete row is reported as `<filename>:<line_number>: <row text>` to stderr; the count of failures is shown in the heading. |
| 6.2 | [x] | [x] | [x] | As a developer, I can be offered three options on SRS gate failure (open files in `$EDITOR` and re-check, skip gate, or abort) so that I can fix incomplete requirements and re-check without restarting the script. Acceptance: option 1 opens all SRS files in `$EDITOR` then re-scans; option 2 continues with a warning; option 3 exits. Default is abort (option 3). |
| 6.3 | [x] | [x] | [x] | As a CI operator, I can pass `--skip-srs` to bypass the SRS gate so that releases can proceed when incomplete requirements are intentional (e.g. partial releases). Acceptance: `--skip-srs` prints a warning and skips the scan entirely; the `srs_skipped: true` flag appears in `--output-json` and in the final report. |

---

## 7.0 README Future Features

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 7.1 | [x] | [x] | [x] | As a developer, I can be shown a numbered list of un-struck items in the `## Future Features` section of `README.md` and asked which ones to mark as implemented so that the README stays current with each release. Acceptance: un-struck items are numbered lines in the section that do not start with `~~`; the prompt accepts comma-separated numbers. |
| 7.2 | [x] | [x] | [x] | As a release engineer, I can pass `--strike-features 1,3,5` to pre-answer which features to mark as implemented so that README updates are scriptable. Acceptance: the script applies strikethroughs for the given numbers without prompting; invalid numbers are silently skipped. |
| 7.3 | [x] | [x] | [x] | As a CI operator, I can pass `--no-readme-update` to skip the Future Features step entirely so that automated releases that don't involve README changes don't need to enumerate feature numbers. Acceptance: `--no-readme-update` skips the `process_readme_features()` call and logs a single ok message. In `--non-interactive` mode without `--strike-features` or `--no-readme-update`, the step is skipped automatically with a log message. |

---

## 8.0 Dry-Run Mode

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 8.1 | [x] | [x] | [x] | As a developer, I can pass `--dry-run` so that all write operations (git commits, file writes, pushes) are printed as `[dry-run]` messages instead of being executed, allowing a full preview of the release workflow without making any changes. Acceptance: `git()` with `write=True` prints and returns `""`; file write helpers print instead of writing; the script exits 0 with no git state changed. |
| 8.2 | [x] | [x] | [x] | As a developer, I can combine `--dry-run` with any other flag (e.g. `--bump minor --no-editor`) so that I can preview exactly what a specific automated invocation would do. Acceptance: all flag combinations that work in live mode work identically in dry-run mode. |

---

## 9.0 Merge Conflict Recovery

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 9.1 | [x] | [x] | [x] | As a developer, I can be shown which files are conflicted when `git merge dev --no-ff` fails with conflicts and be offered two options (abort merge and return to dev, or resolve manually and continue) so that merge conflicts don't require starting the release over from scratch. Acceptance: conflicted files are listed; option 1 (default) runs `git merge --abort` and `git checkout dev`, prints a recovery tip, and exits; option 2 waits for the user to resolve then verifies no conflicts remain. |
| 9.2 | [x] | [x] | [x] | As a CI operator, I can have the script abort the merge automatically and exit non-zero when a conflict occurs in `--non-interactive` mode so that the pipeline detects the failure without hanging. Acceptance: in `--non-interactive` mode, a merge conflict triggers `git merge --abort`, `git checkout dev`, and `sys.exit(1)` without any prompts. |

---

## 10.0 Non-Interactive / CI Mode

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 10.1 | N/A | [x] | [x] | As a CI operator, I can pass `--non-interactive` to disable all prompts so that the script can be driven entirely by flags and exits non-zero on any condition that would normally require human input. Acceptance: `--non-interactive` without `--bump` exits immediately before any git ops; any other prompt-requiring condition (dirty tree, diverge, SRS failure, version mismatch) exits non-zero with a clear error listing which flag to add. |
| 10.2 | N/A | [x] | [x] | As a CI operator, I can have `--non-interactive` validated before any git operations run so that a misconfigured invocation doesn't leave the repo in a partially modified state. Acceptance: the `--bump` check runs in `main()` before `step1_verify_and_sync()` is called. |
| 10.3 | N/A | [x] | [x] | As a CI operator, I can run a fully non-interactive release with `--non-interactive --bump patch --no-ios-bump --no-sync-bump --no-editor --no-readme-update --skip-srs` and have it complete with exit code 0 (or exit non-zero with a diagnostic if any git precondition fails). Acceptance: no prompts are shown; the complete 6-step workflow runs; exit code reflects success or failure. |

---

## 11.0 Reporting and Output Formats

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 11.1 | [x] | [x] | [x] | As a developer, I can see a color-coded final report showing the release tag, next dev version, iOS version (if bumped), sync-client version (if bumped), and recent commits on `main` so that I can verify the release outcome at a glance. Acceptance: the report is printed after step 6; it is suppressed by `--quiet`. |
| 11.2 | N/A | [x] | [x] | As a CI operator, I can pass `--output-json` to receive a machine-readable JSON object on stdout after a successful release so that the pipeline can extract metadata (tag, versions) without parsing human output. Acceptance: `{"tag", "release_version", "next_dev", "ios_version", "sync_version", "srs_skipped"}` is printed as a single JSON line to stdout on success; not printed on failure. |
| 11.3 | [x] | [x] | [x] | As a CI operator, I can pass `--quiet` to suppress all ok/info/section output so that stdout is clean for `--output-json` parsing. Acceptance: `ok()` and `section()` produce no output; `warn()` and `err()` still go to stderr; `--quiet --output-json` produces only the JSON line on stdout. |
| 11.4 | [x] | [x] | [x] | As a CI operator, I can pass `--no-color` (or pipe stdout to a file) to disable ANSI codes so that log files don't contain escape sequences. Acceptance: `--no-color` sets all color constants to `""`; the same effect is triggered automatically when `sys.stdout.isatty()` returns False. |

---

## 12.0 Edge Cases and Safety

| ID | Interactive | Automated | Scripted | Requirement |
|----|:-----------:|:---------:|:--------:|-------------|
| 12.1 | [x] | [x] | [x] | As a developer, I can be offered a recovery menu when the VERSION in `main` after the merge does not match the expected release version so that a merge that silently overwrote the version file is caught before tagging. Acceptance: the menu offers: show git diff and abort (default/recommended), fix manually then re-verify, or accept mismatch with explicit YES confirmation; `--non-interactive` always exits immediately on mismatch. |
| 12.2 | [x] | [x] | [x] | As a release engineer, I can pass `--no-push` to complete all local steps (version files, commit, tag, next-dev commit) without pushing to the remote so that the local release can be inspected before the push. Acceptance: push is skipped; a warning is printed with the manual push command; the final report and `--output-json` still run. |
| 12.3 | [x] | [x] | [x] | As a release engineer, I can pass `--no-delete-branches` to skip merged branch cleanup so that branch cleanup can be deferred or managed separately. Acceptance: `_delete_merged_branches()` is not called; an ok message is logged. |
| 12.4 | [x] | [x] | [x] | As a developer, I can pass `--allow-no-commits` to continue even when `dev` has no commits ahead of `main` so that I can re-run the script after a failed push without going through an interactive menu. Acceptance: the "no commits" check skips the recovery menu and prints a warning; `--non-interactive` without `--allow-no-commits` exits non-zero when no commits are found. |
| 12.5 | [x] | [x] | [x] | As a developer, I can have the auto-stash popped even if the script exits due to an error so that stashed changes are not accidentally abandoned. Acceptance: `_stash_pop()` is called in a `try/finally` block in `main()`; it is a no-op if no stash was created. |
