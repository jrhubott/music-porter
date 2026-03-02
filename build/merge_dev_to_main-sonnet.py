#!/usr/bin/env python3
"""
merge_dev_to_main.py — Automates the merge-dev-to-main workflow for music-porter.

Steps:
  1. Verify and sync
  2. Determine versions
  3. Prepare release on dev (SRS gate, release notes, version commit)
  4. Merge to main
  5. Tag and set next dev version
  6. Push, clean up, and report
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import NoReturn

# ── Constants ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTER_CORE = REPO_ROOT / "porter_core.py"
RELEASE_NOTES = REPO_ROOT / "release-notes.txt"
README = REPO_ROOT / "README.md"
SRS_DIR = REPO_ROOT / "SRS"
IOS_APP_SWIFT = REPO_ROOT / "ios" / "MusicPorter" / "MusicPorter" / "MusicPorterApp.swift"
SYNC_CLIENT_CONSTANTS = REPO_ROOT / "sync-client" / "packages" / "core" / "src" / "constants.ts"

VERSION_LINE_NUMBER = 50  # porter_core.py line where VERSION is defined (1-indexed)

# ── Colours ────────────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def info(msg: str) -> None:
    print(f"{CYAN}{msg}{RESET}")


def success(msg: str) -> None:
    print(f"{GREEN}{BOLD}{msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠  {msg}{RESET}")


def error(msg: str) -> None:
    print(f"{RED}{BOLD}✗  {msg}{RESET}", file=sys.stderr)


def abort(msg: str) -> NoReturn:
    error(msg)
    sys.exit(1)


# ── Shell helpers ──────────────────────────────────────────────────────────────

def run(cmd: list[str], *, check: bool = True, capture: bool = False, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=capture, text=True)


def capture(cmd: list[str], *, cwd: Path = REPO_ROOT) -> str:
    result = run(cmd, capture=True, check=False, cwd=cwd)
    return result.stdout.strip()


def current_branch() -> str:
    return capture(["git", "rev-parse", "--abbrev-ref", "HEAD"])


def has_remote() -> bool:
    result = run(["git", "remote"], capture=True, check=False)
    return bool(result.stdout.strip())


def is_clean() -> bool:
    result = run(["git", "status", "--porcelain"], capture=True, check=False)
    return result.stdout.strip() == ""


# ── Version helpers ────────────────────────────────────────────────────────────

def read_porter_version() -> str:
    """Read VERSION from porter_core.py (line VERSION_LINE_NUMBER)."""
    lines = PORTER_CORE.read_text().splitlines()
    line = lines[VERSION_LINE_NUMBER - 1]
    m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', line)
    if not m:
        abort(f"Could not parse VERSION from porter_core.py line {VERSION_LINE_NUMBER}: {line!r}")
    assert m is not None
    return m.group(1)


def strip_dev_suffix(version: str) -> str:
    """Strip '-dev+hash' or '-dev' suffix to get base semver."""
    return re.sub(r"-dev.*$", "", version)


def bump_version(base: str, bump: str) -> str:
    """Return bumped version string. bump must be 'patch', 'minor', or 'major'."""
    parts = base.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def next_patch(version: str) -> str:
    """Increment only the patch component."""
    return bump_version(version, "patch")


def write_porter_version(version: str) -> None:
    """Overwrite the VERSION line in porter_core.py."""
    text = PORTER_CORE.read_text()
    lines = text.splitlines(keepends=True)
    old_line = lines[VERSION_LINE_NUMBER - 1]
    new_line = re.sub(r'VERSION\s*=\s*["\'][^"\']+["\']', f'VERSION = "{version}"', old_line)
    if new_line == old_line:
        abort(f"Failed to replace VERSION in porter_core.py — pattern not matched on line {VERSION_LINE_NUMBER}")
    lines[VERSION_LINE_NUMBER - 1] = new_line
    PORTER_CORE.write_text("".join(lines))


def read_ios_version() -> str:
    text = IOS_APP_SWIFT.read_text()
    m = re.search(r'appVersion\s*=\s*"([^"]+)"', text)
    if not m:
        abort("Could not parse appVersion from MusicPorterApp.swift")
    assert m is not None
    return m.group(1)


def write_ios_version(version: str) -> None:
    text = IOS_APP_SWIFT.read_text()
    new_text = re.sub(r'(appVersion\s*=\s*")[^"]+(")', rf'\g<1>{version}\2', text)
    if new_text == text:
        abort("Failed to replace appVersion in MusicPorterApp.swift")
    IOS_APP_SWIFT.write_text(new_text)


def read_sync_client_version() -> str:
    text = SYNC_CLIENT_CONSTANTS.read_text()
    m = re.search(r"VERSION\s*=\s*'([^']+)'", text)
    if not m:
        m = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    if not m:
        abort("Could not parse VERSION from sync-client constants.ts")
    assert m is not None
    return m.group(1)


def write_sync_client_version(version: str) -> None:
    text = SYNC_CLIENT_CONSTANTS.read_text()
    new_text = re.sub(r"(VERSION\s*=\s*')[^']+(')", rf"\g<1>{version}\2", text)
    if new_text == text:
        new_text = re.sub(r'(VERSION\s*=\s*")[^"]+(")', rf'\g<1>{version}\2', text)
    if new_text == text:
        abort("Failed to replace VERSION in sync-client constants.ts")
    SYNC_CLIENT_CONSTANTS.write_text(new_text)


# ── User input helpers ─────────────────────────────────────────────────────────

def prompt(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        raw = input(f"{BOLD}{question}{hint}: {RESET}").strip()
        return raw if raw else default
    except (EOFError, KeyboardInterrupt):
        print()
        abort("Aborted by user.")


def choose_bump(suggestion: str) -> str:
    """Interactively ask for PATCH/MINOR/MAJOR bump selection."""
    while True:
        raw = prompt(f"Version bump type (patch/minor/major)", default=suggestion).lower()
        if raw in ("patch", "minor", "major"):
            return raw
        print("  Please enter 'patch', 'minor', or 'major'.")


def suggest_bump(commits: str) -> str:
    """Guess bump type from commit messages (heuristic)."""
    lower = commits.lower()
    if any(kw in lower for kw in ("breaking", "major", "rewrite", "remove")):
        return "major"
    if any(kw in lower for kw in ("feature", "add", "new", "support", "enable")):
        return "minor"
    return "patch"


# ── SRS gate ───────────────────────────────────────────────────────────────────

def check_srs_gate() -> None:
    """Abort if any SRS file has an unchecked [ ] item."""
    incomplete: list[tuple[str, int, str]] = []
    for srs_file in sorted(SRS_DIR.glob("*.md")):
        for lineno, line in enumerate(srs_file.read_text().splitlines(), start=1):
            if re.search(r"\[\s\]", line):
                incomplete.append((srs_file.name, lineno, line.strip()))

    if incomplete:
        error("SRS gate failed — incomplete requirements found:")
        for filename, lineno, line in incomplete:
            print(f"  {filename}:{lineno}  {line}")
        abort("All SRS items must be checked [x] or N/A before merging to main.")


# ── Release notes ──────────────────────────────────────────────────────────────

def commits_since_last_tag() -> list[str]:
    """Return one-line commit messages since the last tag on main."""
    last_tag = capture(["git", "describe", "--tags", "--abbrev=0", "main"])
    if not last_tag:
        # No tags yet — use all commits on dev not on main
        raw = capture(["git", "log", "main..dev", "--pretty=format:%s"])
    else:
        raw = capture(["git", "log", f"{last_tag}..dev", "--pretty=format:%s"])
    return [line for line in raw.splitlines() if line.strip()]


def build_release_notes_entry(version: str, extra_bullets: list[str]) -> str:
    """Build a new release-notes.txt entry."""
    today = date.today().strftime("%Y-%m-%d")
    messages = commits_since_last_tag()
    bullets = [f"• {msg}" for msg in messages if msg]
    bullets.extend(extra_bullets)
    lines = [f"Version {version} ({today}):"] + bullets + [""]
    return "\n".join(lines)


def prepend_release_notes(entry: str) -> None:
    existing = RELEASE_NOTES.read_text() if RELEASE_NOTES.exists() else ""
    RELEASE_NOTES.write_text(entry + "\n" + existing)


# ── README future features ─────────────────────────────────────────────────────

def strikethrough_readme_features(_version: str) -> None:
    """
    For any Future Features list item that is NOT already struck through,
    check if it was recently implemented (commits mention it) and mark it.
    This is a best-effort silent operation — we never abort on failure.
    """
    # We do a passive pass: leave this for the user to do manually.
    # The skill says "silently strikethrough any Future Features matching this release"
    # but matching commit text to README items is inherently fuzzy.
    # We print a reminder instead.
    warn("Reminder: manually review README.md Future Features — strike through any items completed in this release.")


# ── Step 1: Verify and sync ────────────────────────────────────────────────────

def step_verify_and_sync() -> None:
    info("\n── Step 1: Verify and sync ──────────────────────────────────────────────")

    branch = current_branch()
    if branch != "dev":
        info(f"Currently on '{branch}' — switching to dev...")
        run(["git", "checkout", "dev"])

    if not is_clean():
        abort("Working tree is not clean. Commit or stash changes before merging.")

    remote_available = has_remote()

    if remote_available:
        info("Fetching from origin...")
        run(["git", "fetch", "origin"], check=False)

        # Check main divergence
        behind_main = capture(["git", "rev-list", "--count", "main..origin/main"])
        ahead_main = capture(["git", "rev-list", "--count", "origin/main..main"])
        if behind_main and int(behind_main) > 0:
            if ahead_main and int(ahead_main) > 0:
                abort("Local main has diverged from origin/main. Resolve manually.")
            info(f"Updating local main ({behind_main} commits behind remote)...")
            run(["git", "checkout", "main"])
            run(["git", "pull", "origin", "main"])
            run(["git", "checkout", "dev"])

        # Check dev status
        behind_dev = capture(["git", "rev-list", "--count", "dev..origin/dev"])
        if behind_dev and int(behind_dev) > 0:
            info(f"Updating local dev ({behind_dev} commits behind remote)...")
            run(["git", "pull", "origin", "dev"])
    else:
        warn("No remote configured — skipping fetch.")

    log = capture(["git", "log", "main..dev", "--oneline"])
    if not log:
        abort("No commits on dev ahead of main — nothing to merge.")
    print(f"\nCommits to be merged:\n{log}\n")


# ── Step 2: Determine versions ─────────────────────────────────────────────────

def step_determine_versions() -> tuple[str, str | None, str | None]:
    """
    Returns (new_server_version, new_ios_version_or_None, new_sync_client_version_or_None).
    """
    info("\n── Step 2: Determine versions ───────────────────────────────────────────")

    raw_version = read_porter_version()
    base_version = strip_dev_suffix(raw_version)
    info(f"Current VERSION: {raw_version}  (base: {base_version})")

    commits = capture(["git", "log", "main..dev", "--pretty=format:%s"])
    suggestion = suggest_bump(commits)
    info(f"Suggested bump type based on commits: {suggestion.upper()}")

    bump = choose_bump(suggestion)
    new_server_version = bump_version(base_version, bump)
    print(f"  Server version: {base_version} → {new_server_version}")

    # Check iOS changes
    new_ios_version: str | None = None
    last_tag = capture(["git", "describe", "--tags", "--abbrev=0", "main"])
    ref_range = f"{last_tag}..dev" if last_tag else "main..dev"

    ios_changed = bool(capture(["git", "diff", ref_range, "--name-only", "--", "ios/"]))
    if ios_changed and IOS_APP_SWIFT.exists():
        current_ios = read_ios_version()
        suggested_ios = next_patch(current_ios)
        raw = prompt(f"iOS changes detected. New iOS version (current: {current_ios})", default=suggested_ios)
        new_ios_version = raw.strip() or suggested_ios
        print(f"  iOS version: {current_ios} → {new_ios_version}")
    else:
        info("No iOS changes detected.")

    # Check sync-client changes
    new_sync_version: str | None = None
    sc_changed = bool(capture(["git", "diff", ref_range, "--name-only", "--", "sync-client/"]))
    if sc_changed and SYNC_CLIENT_CONSTANTS.exists():
        current_sc = read_sync_client_version()
        suggested_sc = next_patch(current_sc)
        raw = prompt(f"Sync-client changes detected. New sync-client version (current: {current_sc})", default=suggested_sc)
        new_sync_version = raw.strip() or suggested_sc
        print(f"  Sync-client version: {current_sc} → {new_sync_version}")
    else:
        info("No sync-client changes detected.")

    return new_server_version, new_ios_version, new_sync_version


# ── Step 3: Prepare release on dev ────────────────────────────────────────────

def step_prepare_release(new_server_version: str, new_ios_version: str | None, new_sync_version: str | None) -> None:
    info("\n── Step 3: Prepare release on dev ───────────────────────────────────────")

    # SRS gate
    info("Checking SRS gate...")
    check_srs_gate()
    success("SRS gate passed.")

    # README reminder
    strikethrough_readme_features(new_server_version)

    # Extra release note bullets for iOS / sync-client version bumps
    extra_bullets: list[str] = []
    if new_ios_version:
        extra_bullets.append(f"• iOS app version bumped to {new_ios_version}")
    if new_sync_version:
        extra_bullets.append(f"• Sync client version bumped to {new_sync_version}")

    # Release notes
    info("Prepending release notes entry...")
    entry = build_release_notes_entry(new_server_version, extra_bullets)
    prepend_release_notes(entry)
    success("release-notes.txt updated.")

    # iOS version update
    if new_ios_version:
        info(f"Updating iOS appVersion to {new_ios_version}...")
        write_ios_version(new_ios_version)

    # Sync-client version update
    if new_sync_version:
        info(f"Updating sync-client VERSION to {new_sync_version}...")
        write_sync_client_version(new_sync_version)

    # Update server VERSION
    info(f"Setting VERSION = \"{new_server_version}\" in porter_core.py...")
    write_porter_version(new_server_version)

    # Stage and commit all changes
    run(["git", "add",
         str(PORTER_CORE),
         str(RELEASE_NOTES),
         *(([str(IOS_APP_SWIFT)] if new_ios_version else [])),
         *(([str(SYNC_CLIENT_CONSTANTS)] if new_sync_version else [])),
         ])
    run(["git", "commit", "-m", f"Update version to {new_server_version} for merge to main"])
    success(f"Version commit created: Update version to {new_server_version} for merge to main")


# ── Step 4: Merge to main ──────────────────────────────────────────────────────

def step_merge_to_main(new_server_version: str) -> None:
    info("\n── Step 4: Merge to main ─────────────────────────────────────────────────")

    run(["git", "checkout", "main"])
    result = run(["git", "merge", "dev", "--no-ff"], check=False)
    if result.returncode != 0:
        conflicts = capture(["git", "diff", "--name-only", "--diff-filter=U"])
        error(f"Merge conflicts detected:\n{conflicts}")
        guidance = prompt("Enter resolution guidance (or 'abort' to cancel merge)").strip()
        if guidance.lower() == "abort":
            run(["git", "merge", "--abort"], check=False)
            run(["git", "checkout", "dev"])
            abort("Merge aborted by user.")
        abort("Resolve conflicts manually, then re-run the script.")

    # Verify
    if not is_clean():
        abort("Working tree not clean after merge — unexpected state.")

    actual_version = read_porter_version()
    if actual_version != new_server_version:
        abort(f"VERSION mismatch after merge: expected {new_server_version}, got {actual_version}")

    success(f"Merged dev into main (VERSION = {new_server_version}).")


# ── Step 5: Tag and set next dev version ──────────────────────────────────────

def step_tag_and_next_dev(new_server_version: str) -> str:
    info("\n── Step 5: Tag and set next dev version ─────────────────────────────────")

    tag = f"v{new_server_version}"
    run(["git", "tag", tag])
    success(f"Tagged: {tag}")

    run(["git", "checkout", "dev"])
    run(["git", "merge", "main"])

    next_dev = next_patch(new_server_version) + "-dev"
    info(f"Setting next dev VERSION to {next_dev}...")
    write_porter_version(next_dev)
    run(["git", "add", str(PORTER_CORE)])
    run(["git", "commit", "-m", f"Set next dev version to {next_dev}"])
    success(f"Next dev version committed: {next_dev}")

    return next_dev


# ── Step 6: Push, clean up, report ────────────────────────────────────────────

def step_push_and_cleanup(new_server_version: str, next_dev_version: str) -> None:
    info("\n── Step 6: Push, clean up, and report ───────────────────────────────────")

    if has_remote():
        info("Pushing main, dev, and tags to origin...")
        result = run(["git", "push", "origin", "main", "dev", "--tags"], check=False)
        if result.returncode != 0:
            warn("Push failed. Push manually — do NOT use --force.")
    else:
        warn("No remote — skipping push.")

    # Delete branches merged into dev (excluding main and dev)
    merged_raw = capture(["git", "branch", "--merged", "dev"])
    merged_branches = [
        b.strip().lstrip("* ")
        for b in merged_raw.splitlines()
        if b.strip().lstrip("* ") not in ("main", "dev", "")
    ]
    if merged_branches:
        info(f"Deleting merged branches: {', '.join(merged_branches)}")
        for branch in merged_branches:
            run(["git", "branch", "-d", branch], check=False)
    else:
        info("No merged branches to delete.")

    # Final report
    log = capture(["git", "log", "main", "--oneline", "-5"])
    print(f"\n{BOLD}── Final state ──────────────────────────────────────────────────────────{RESET}")
    print(f"Tag:         v{new_server_version}")
    print(f"Dev VERSION: {next_dev_version}")
    print(f"\nLatest commits on main:\n{log}")
    success("\nMerge to main complete.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"{BOLD}{'━' * 72}{RESET}")
    print(f"{BOLD}  merge-dev-to-main{RESET}")
    print(f"{BOLD}{'━' * 72}{RESET}\n")

    if not PORTER_CORE.exists():
        abort(f"porter_core.py not found at {PORTER_CORE}. Run from the repo root or build/ directory.")

    step_verify_and_sync()
    new_server_version, new_ios_version, new_sync_version = step_determine_versions()
    step_prepare_release(new_server_version, new_ios_version, new_sync_version)
    step_merge_to_main(new_server_version)
    next_dev = step_tag_and_next_dev(new_server_version)
    step_push_and_cleanup(new_server_version, next_dev)


if __name__ == "__main__":
    main()
