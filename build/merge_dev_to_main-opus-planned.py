#!/usr/bin/env python3
"""merge_dev_to_main-opus-planned.py — Standalone release workflow for music-porter.

Replicates the /merge-dev-to-main skill workflow as an interactive CLI tool.
Run from the project root or any subdirectory of it.

Usage:
    ./build/merge_dev_to_main-opus-planned.py [--dry-run] [--skip-srs]
    python3 build/merge_dev_to_main-opus-planned.py [--dry-run] [--skip-srs]

Steps:
    1. Verify and sync  — switch to dev, check clean, fetch, show commit log
    2. Determine versions — read versions, check iOS/sync-client changes, prompt bumps
    3. Prepare release  — SRS gate, README, release notes, version files, commit
    4. Merge to main    — checkout main, merge dev --no-ff, verify
    5. Tag & next dev   — create tag, merge back to dev, set next -dev version
    6. Push & clean up  — push to remote, delete merged branches, final report
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# Constants — no magic literals in logic
# ══════════════════════════════════════════════════════════════════════════════

MAIN_BRANCH = "main"
DEV_BRANCH = "dev"
VERSION_FILE = "porter_core.py"
IOS_VERSION_FILE = "ios/MusicPorter/MusicPorter/MusicPorterApp.swift"
SYNC_VERSION_FILE = "sync-client/packages/core/src/constants.ts"
RELEASE_NOTES_FILE = "release-notes.txt"
README_FILE = "README.md"
SRS_GLOB = "SRS/*.md"
FINAL_LOG_COUNT = 5  # recent commits shown in final report
EDITOR_FALLBACK = "vi"

# Regex patterns for locating version strings in source files
RE_PORTER_VERSION = re.compile(r'(VERSION\s*=\s*")[^"]+(")', re.MULTILINE)
RE_IOS_VERSION = re.compile(r'(static let appVersion\s*=\s*")[^"]+"')
RE_SYNC_VERSION = re.compile(r"(export const VERSION\s*=\s*')[^']+'")
RE_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)")

# Patterns for SRS completeness check and README feature detection
RE_SRS_UNCHECKED = re.compile(r"\|\s*\[\s*\]\s*\|")
RE_FUTURE_FEATURES_HEADER = re.compile(r"^#{1,2}\s+Future Features")
RE_NEXT_H2 = re.compile(r"^##\s+\w")
RE_UNIMPLEMENTED_FEATURE = re.compile(r"^(\d+\.\s+)(?!~~)(.*)")

# Commit message prefixes to exclude from release notes (housekeeping)
HOUSEKEEPING_PREFIXES = (
    "set next dev version",
    "update version to",
    "merge branch",
    "merge remote-tracking",
)

# ANSI color/style codes
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"

# ══════════════════════════════════════════════════════════════════════════════
# Module-level globals — set once in main()
# ══════════════════════════════════════════════════════════════════════════════

DRY_RUN: bool = False
SKIP_SRS: bool = False
PROJECT_ROOT: Path = Path(".")

# ══════════════════════════════════════════════════════════════════════════════
# Output helpers
# ══════════════════════════════════════════════════════════════════════════════


def ok(msg: str) -> None:
    """Print a success/info message."""
    print(f"{C_GREEN}✓{C_RESET} {msg}")


def warn(msg: str) -> None:
    """Print a warning."""
    print(f"{C_YELLOW}⚠{C_RESET}  {msg}")


def err(msg: str) -> None:
    """Print an error to stderr."""
    print(f"{C_RED}✗{C_RESET} {msg}", file=sys.stderr)


def section(title: str) -> None:
    """Print a bold section header."""
    bar = "─" * 60
    print(f"\n{C_BOLD}{C_CYAN}{bar}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}  {title}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}{bar}{C_RESET}")


def dry(msg: str) -> None:
    """Print a dry-run placeholder for a write operation."""
    print(f"{C_CYAN}[dry-run]{C_RESET} {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# Interactive helpers
# ══════════════════════════════════════════════════════════════════════════════


def ask(prompt_text: str, default: str = "") -> str:
    """Prompt the user for input with an optional default."""
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"{prompt_text}{suffix}: ").strip()
        return raw if raw else default
    except KeyboardInterrupt:
        print()
        err("Aborted.")
        sys.exit(1)
    except EOFError:
        return default


def confirm(question: str, default: bool = True) -> bool:
    """Ask a yes/no question, return True for yes."""
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"{question} [{hint}]: ").strip().lower()
        if not raw:
            return default
        return raw in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        err("Aborted.")
        sys.exit(1)


def abort(msg: str) -> None:
    """Print an error message and exit with failure."""
    err(msg)
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# Git wrapper
# ══════════════════════════════════════════════════════════════════════════════


def git(args: list[str], *, write: bool = False, check: bool = True) -> str:
    """Run a git command rooted at PROJECT_ROOT and return stdout.

    Write operations (write=True) are intercepted in dry-run mode: the command
    is printed but not executed, and an empty string is returned.  Read
    operations always execute regardless of dry-run.

    Raises subprocess.CalledProcessError on non-zero exit when check=True.
    """
    if DRY_RUN and write:
        dry("git " + " ".join(args))
        return ""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
    except FileNotFoundError:
        abort("git not found in PATH.")
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            ["git", *args],
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout


def has_remote(name: str = "origin") -> bool:
    """Return True if the given remote exists."""
    return name in git(["remote"]).split()


# ══════════════════════════════════════════════════════════════════════════════
# Version helpers
# ══════════════════════════════════════════════════════════════════════════════


def semver_parts(version: str) -> tuple[int, int, int]:
    """Extract (major, minor, patch) integers from a semver string."""
    m = RE_SEMVER.match(version)
    if not m:
        abort(f"Cannot parse semver from: {version!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def apply_bump(base: str, bump: str) -> str:
    """Return new version string after applying PATCH / MINOR / MAJOR bump."""
    major, minor, patch = semver_parts(base)
    if bump == "MAJOR":
        return f"{major + 1}.0.0"
    if bump == "MINOR":
        return f"{major}.{minor + 1}.0"
    # Default: PATCH
    return f"{major}.{minor}.{patch + 1}"


def next_dev_version(release: str) -> str:
    """Given release version '2.38.0', return the next dev version '2.38.1-dev'."""
    major, minor, patch = semver_parts(release)
    return f"{major}.{minor}.{patch + 1}-dev"


def strip_dev_suffix(version: str) -> str:
    """Strip any '-dev+hash' or '-branchname' suffix and return bare semver."""
    m = RE_SEMVER.match(version)
    if not m:
        abort(f"Cannot parse base version from: {version!r}")
    return m.group(0)


def patch_bump(version: str) -> str:
    """Return PATCH-bumped version string (e.g. '1.6.1' → '1.6.2')."""
    major, minor, patch = semver_parts(version)
    return f"{major}.{minor}.{patch + 1}"


# ══════════════════════════════════════════════════════════════════════════════
# File read / write helpers
# ══════════════════════════════════════════════════════════════════════════════


def read_porter_version() -> str:
    """Read the raw VERSION value from porter_core.py (includes -dev+hash suffix)."""
    text = (PROJECT_ROOT / VERSION_FILE).read_text()
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        abort(f"Cannot find VERSION in {VERSION_FILE}.")
    return m.group(1)


def write_porter_version(version: str) -> None:
    """Set VERSION = "version" in porter_core.py."""
    if DRY_RUN:
        dry(f'Set VERSION = "{version}" in {VERSION_FILE}')
        return
    path = PROJECT_ROOT / VERSION_FILE
    text = path.read_text()
    new_text, n = RE_PORTER_VERSION.subn(rf"\g<1>{version}\g<2>", text)
    if n == 0:
        abort(f"Could not update VERSION in {VERSION_FILE}.")
    path.write_text(new_text)
    ok(f'Updated {VERSION_FILE}: VERSION = "{version}"')


def read_ios_version() -> str:
    """Read the appVersion from MusicPorterApp.swift."""
    text = (PROJECT_ROOT / IOS_VERSION_FILE).read_text()
    m = re.search(r'static let appVersion\s*=\s*"([^"]+)"', text)
    if not m:
        abort(f"Cannot find appVersion in {IOS_VERSION_FILE}.")
    return m.group(1)


def write_ios_version(version: str) -> None:
    """Set the appVersion in MusicPorterApp.swift."""
    if DRY_RUN:
        dry(f'Set appVersion = "{version}" in {IOS_VERSION_FILE}')
        return
    path = PROJECT_ROOT / IOS_VERSION_FILE
    text = path.read_text()
    new_text, n = RE_IOS_VERSION.subn(rf'\g<1>{version}"', text)
    if n == 0:
        abort(f"Could not update appVersion in {IOS_VERSION_FILE}.")
    path.write_text(new_text)
    ok(f"Updated iOS appVersion → {version}")


def read_sync_version() -> str:
    """Read the VERSION from sync-client/packages/core/src/constants.ts."""
    text = (PROJECT_ROOT / SYNC_VERSION_FILE).read_text()
    m = re.search(r"export const VERSION\s*=\s*'([^']+)'", text)
    if not m:
        abort(f"Cannot find VERSION in {SYNC_VERSION_FILE}.")
    return m.group(1)


def write_sync_version(version: str) -> None:
    """Set the VERSION in sync-client constants.ts."""
    if DRY_RUN:
        dry(f"Set VERSION = '{version}' in {SYNC_VERSION_FILE}")
        return
    path = PROJECT_ROOT / SYNC_VERSION_FILE
    text = path.read_text()
    new_text, n = RE_SYNC_VERSION.subn(rf"\g<1>{version}'", text)
    if n == 0:
        abort(f"Could not update VERSION in {SYNC_VERSION_FILE}.")
    path.write_text(new_text)
    ok(f"Updated sync-client VERSION → {version}")


def prepend_release_notes(entry: str) -> None:
    """Prepend a new release notes entry to release-notes.txt."""
    if DRY_RUN:
        dry(f"Prepend to {RELEASE_NOTES_FILE}:\n{entry}")
        return
    path = PROJECT_ROOT / RELEASE_NOTES_FILE
    existing = path.read_text() if path.exists() else ""
    path.write_text(entry + "\n" + existing)
    ok(f"Updated {RELEASE_NOTES_FILE}")


# ══════════════════════════════════════════════════════════════════════════════
# Release notes
# ══════════════════════════════════════════════════════════════════════════════


def build_release_notes_draft(version: str, last_tag: str) -> str:
    """Generate a draft release notes entry from commits since last_tag."""
    today = datetime.now().strftime("%Y-%m-%d")
    # Build log range: from last tag to dev, or all of dev if no tag yet
    if last_tag:
        log_range = f"{last_tag}..{DEV_BRANCH}"
    else:
        log_range = DEV_BRANCH
    raw = git(["log", log_range, "--oneline", "--no-merges"]).strip()

    bullets: list[str] = []
    for line in raw.splitlines():
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        msg = parts[1].strip()
        if any(msg.lower().startswith(p) for p in HOUSEKEEPING_PREFIXES):
            continue
        bullets.append(f"• {msg}")

    if not bullets:
        bullets = ["• Various improvements and fixes"]

    return f"Version {version} ({today}):\n" + "\n".join(bullets) + "\n"


def edit_in_editor(content: str) -> str:
    """Open content in $EDITOR (or vi) and return the edited text."""
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", EDITOR_FALLBACK))
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="release-notes-",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        subprocess.run([editor, tmp_path], check=True)
        return Path(tmp_path).read_text()
    except FileNotFoundError:
        warn(f"Editor '{editor}' not found — skipping edit.")
        return content
    except subprocess.CalledProcessError:
        warn("Editor exited with error — using unedited draft.")
        return content
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# README future features
# ══════════════════════════════════════════════════════════════════════════════


def find_unimplemented_features(text: str) -> list[tuple[int, str]]:
    """Return (line_index, line_text) for un-struck numbered items in Future Features.

    Scans between the '## Future Features' heading and the next h2 heading.
    Un-struck items are numbered lines that do NOT begin with '~~'.
    """
    lines = text.splitlines()
    in_section = False
    results: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if RE_FUTURE_FEATURES_HEADER.match(stripped):
            in_section = True
            continue
        if in_section and RE_NEXT_H2.match(stripped):
            break
        if in_section and RE_UNIMPLEMENTED_FEATURE.match(stripped):
            results.append((i, line))
    return results


def apply_strikethroughs(
    readme_text: str,
    selected: list[int],
    features: list[tuple[int, str]],
    version: str,
) -> str:
    """Return readme_text with selected feature lines struck through.

    selected is a list of 0-based indices into the features list.
    """
    lines = readme_text.splitlines()
    for idx in set(selected):  # deduplicate in case of repeated input
        line_idx, line_text = features[idx]
        stripped = line_text.strip()
        m = RE_UNIMPLEMENTED_FEATURE.match(stripped)
        if not m:
            continue
        num_prefix = m.group(1)  # e.g. "4. "
        content = m.group(2)  # e.g. "**Feature** - description"
        struck = f"{num_prefix}~~{content}~~ *(implemented in v{version})*"
        leading = len(line_text) - len(line_text.lstrip())
        lines[line_idx] = " " * leading + struck

    result = "\n".join(lines)
    if readme_text.endswith("\n"):
        result += "\n"
    return result


def process_readme_features(version: str) -> None:
    """Interactively ask which Future Features to mark as implemented."""
    readme_path = PROJECT_ROOT / README_FILE
    if not readme_path.exists():
        warn(f"{README_FILE} not found — skipping feature strikethrough.")
        return

    readme_text = readme_path.read_text()
    features = find_unimplemented_features(readme_text)

    if not features:
        ok("No un-struck Future Features in README.")
        return

    print(f"\n{C_BOLD}Unimplemented Future Features:{C_RESET}")
    for i, (_, line) in enumerate(features, 1):
        print(f"  {i:2d}. {line.strip()}")

    print()
    raw = ask("Numbers to mark as implemented in this release (comma-separated, or Enter to skip)")
    if not raw.strip():
        ok("No features marked as implemented.")
        return

    selected: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part)
            if 1 <= n <= len(features):
                selected.append(n - 1)  # convert to 0-based index

    if not selected:
        warn("No valid feature numbers entered — skipping strikethrough.")
        return

    if DRY_RUN:
        dry(f"Strikethrough {len(selected)} feature(s) in {README_FILE}")
        return

    new_text = apply_strikethroughs(readme_text, selected, features, version)
    readme_path.write_text(new_text)
    ok(f"Marked {len(selected)} feature(s) as implemented in {README_FILE}")


# ══════════════════════════════════════════════════════════════════════════════
# SRS gate
# ══════════════════════════════════════════════════════════════════════════════


def check_srs_gate() -> None:
    """Scan SRS/*.md for unchecked client columns.  Abort if any are found.

    Bypass with --skip-srs when incomplete requirements are intentional.
    """
    if SKIP_SRS:
        warn("SRS completeness gate bypassed via --skip-srs.")
        return

    srs_files = sorted(glob.glob(str(PROJECT_ROOT / SRS_GLOB)))
    if not srs_files:
        ok("No SRS files found — gate passed.")
        return

    incomplete: list[str] = []
    for srs_file in srs_files:
        path = Path(srs_file)
        for line_num, line in enumerate(path.read_text().splitlines(), 1):
            if RE_SRS_UNCHECKED.search(line):
                incomplete.append(f"  {path.name}:{line_num}: {line.strip()}")

    if not incomplete:
        ok("SRS gate passed — all requirements are implemented.")
        return

    err("SRS gate FAILED — incomplete requirements found:")
    for item in incomplete:
        print(item, file=sys.stderr)
    abort("Resolve all [ ] items or use --skip-srs to bypass.")


# ══════════════════════════════════════════════════════════════════════════════
# Remote branch sync helpers
# ══════════════════════════════════════════════════════════════════════════════


def sync_branch_from_remote(branch: str) -> None:
    """Fast-forward local branch from remote if behind.  Abort if diverged."""
    try:
        local_sha = git(["rev-parse", branch]).strip()
        remote_sha = git(["rev-parse", f"origin/{branch}"]).strip()
    except subprocess.CalledProcessError:
        # Remote doesn't track this branch — nothing to sync
        return

    if local_sha == remote_sha:
        ok(f"{branch} is up to date with remote.")
        return

    # Is local an ancestor of remote?  If so, we can fast-forward.
    ff_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", local_sha, remote_sha],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    if ff_check.returncode == 0:
        git(["fetch", "origin", f"{branch}:{branch}"], write=True)
        ok(f"Fast-forwarded {branch} from remote.")
        return

    # Is remote an ancestor of local?  Local is ahead — nothing to do.
    ahead_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", remote_sha, local_sha],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    if ahead_check.returncode == 0:
        ok(f"{branch} is ahead of remote — no update needed.")
        return

    abort(
        f"{branch} has diverged from origin/{branch}.\n"
        "  Please reconcile manually before running this script."
    )


# ══════════════════════════════════════════════════════════════════════════════
# VersionInfo dataclass
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class VersionInfo:
    """All version decisions collected in Step 2."""

    base_version: str  # bare semver stripped of -dev+hash, e.g. "2.37.4"
    release_version: str  # version for this release, e.g. "2.38.0"
    next_dev: str  # next dev version, e.g. "2.38.1-dev"
    last_tag: str  # last tag on main, e.g. "v2.37.0" (empty if none)
    ios_changed: bool
    ios_current: str  # current appVersion in MusicPorterApp.swift
    ios_new: str  # user-chosen new iOS version (empty if not changing)
    sync_changed: bool
    sync_current: str  # current VERSION in constants.ts
    sync_new: str  # user-chosen new sync-client version (empty if not changing)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: Verify and sync
# ══════════════════════════════════════════════════════════════════════════════


def step1_verify_and_sync() -> str:
    """Switch to dev, verify clean tree, sync from remote, display commit log."""
    section("Step 1: Verify and Sync")

    current = git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if current != DEV_BRANCH:
        ok(f"Switching from '{current}' to '{DEV_BRANCH}'…")
        git(["checkout", DEV_BRANCH], write=True)

    status = git(["status", "--porcelain"]).strip()
    if status:
        err("Working tree is not clean:")
        for line in status.splitlines():
            print(f"  {line}")
        abort("Commit or stash all changes before running this script.")

    ok("Working tree is clean.")

    if has_remote():
        ok("Fetching from origin…")
        git(["fetch", "origin"], write=True)
        sync_branch_from_remote(MAIN_BRANCH)
        sync_branch_from_remote(DEV_BRANCH)
    else:
        warn("No remote 'origin' found — skipping fetch and sync.")

    commit_log = git(["log", f"{MAIN_BRANCH}..{DEV_BRANCH}", "--oneline"]).strip()
    if not commit_log:
        abort("No commits on dev since main. Nothing to merge.")

    print(f"\n{C_BOLD}Commits to merge ({DEV_BRANCH} → {MAIN_BRANCH}):{C_RESET}")
    for line in commit_log.splitlines():
        print(f"  {line}")

    return commit_log


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: Determine versions
# ══════════════════════════════════════════════════════════════════════════════


def step2_determine_versions() -> VersionInfo:
    """Read current versions, detect component changes, prompt for bump decisions."""
    section("Step 2: Determine Versions")

    raw_version = read_porter_version()
    base_version = strip_dev_suffix(raw_version)
    ok(f"Current dev version: {raw_version}  →  base: {base_version}")

    try:
        last_tag = git(["describe", "--tags", "--abbrev=0", MAIN_BRANCH]).strip()
        ok(f"Last main tag: {last_tag}")
    except subprocess.CalledProcessError:
        last_tag = ""
        warn("No tags found on main — treating all dev history as new.")

    diff_ref = f"{last_tag}..{DEV_BRANCH}" if last_tag else DEV_BRANCH

    ios_files = git(["diff", diff_ref, "--name-only", "--", "ios/"]).strip()
    ios_changed = bool(ios_files)
    ios_current = read_ios_version()
    if ios_changed:
        ok(f"iOS changes detected since {last_tag or 'beginning'} (current: {ios_current})")
    else:
        ok(f"No iOS changes since {last_tag or 'beginning'}.")

    sync_files = git(["diff", diff_ref, "--name-only", "--", "sync-client/"]).strip()
    sync_changed = bool(sync_files)
    sync_current = read_sync_version()
    if sync_changed:
        ok(f"Sync-client changes detected since {last_tag or 'beginning'} (current: {sync_current})")
    else:
        ok(f"No sync-client changes since {last_tag or 'beginning'}.")

    # Prompt: server version bump
    print(f"\n{C_BOLD}Server version bump{C_RESET} (current base: {base_version})")
    print("  1. PATCH (default) — bug fixes and minor improvements")
    print("  2. MINOR — new features, backwards compatible")
    print("  3. MAJOR — breaking changes")
    choice = ask("Bump type", "1").upper()
    if choice in ("2", "MINOR"):
        bump_type = "MINOR"
    elif choice in ("3", "MAJOR"):
        bump_type = "MAJOR"
    else:
        bump_type = "PATCH"
    release_version = apply_bump(base_version, bump_type)
    ok(f"Release version: {release_version} ({bump_type} bump)")
    next_dev = next_dev_version(release_version)

    # Prompt: iOS version (only if changed)
    ios_new = ""
    if ios_changed:
        suggested = patch_bump(ios_current)
        print(f"\n{C_BOLD}iOS version{C_RESET}: current = {ios_current}, suggested = {suggested}")
        ios_new = ask("New iOS appVersion", suggested)
        ok(f"iOS: {ios_current} → {ios_new}")

    # Prompt: sync-client version (only if changed)
    sync_new = ""
    if sync_changed:
        suggested = patch_bump(sync_current)
        print(f"\n{C_BOLD}Sync-client version{C_RESET}: current = {sync_current}, suggested = {suggested}")
        sync_new = ask("New sync-client VERSION", suggested)
        ok(f"Sync-client: {sync_current} → {sync_new}")

    return VersionInfo(
        base_version=base_version,
        release_version=release_version,
        next_dev=next_dev,
        last_tag=last_tag,
        ios_changed=ios_changed,
        ios_current=ios_current,
        ios_new=ios_new,
        sync_changed=sync_changed,
        sync_current=sync_current,
        sync_new=sync_new,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Step 3: Prepare release on dev
# ══════════════════════════════════════════════════════════════════════════════


def step3_prepare_release(vi: VersionInfo) -> None:
    """SRS gate, README, release notes, version files, release commit on dev."""
    section("Step 3: Prepare Release on dev")

    check_srs_gate()
    process_readme_features(vi.release_version)

    # Build release notes draft
    draft = build_release_notes_draft(vi.release_version, vi.last_tag)

    # Append component version bumps as extra bullets
    extra: list[str] = []
    if vi.ios_changed and vi.ios_new:
        extra.append(f"• iOS companion app updated to v{vi.ios_new}")
    if vi.sync_changed and vi.sync_new:
        extra.append(f"• Sync client updated to v{vi.sync_new}")
    if extra:
        draft = draft.rstrip("\n") + "\n" + "\n".join(extra) + "\n"

    print(f"\n{C_BOLD}Draft release notes:{C_RESET}")
    print(draft)

    if confirm("Open in $EDITOR to refine?", default=False):
        draft = edit_in_editor(draft)
        print(f"\n{C_BOLD}Final release notes:{C_RESET}")
        print(draft)

    prepend_release_notes(draft)

    if vi.ios_changed and vi.ios_new:
        write_ios_version(vi.ios_new)

    if vi.sync_changed and vi.sync_new:
        write_sync_version(vi.sync_new)

    write_porter_version(vi.release_version)

    # Stage all modified files and commit
    files_to_stage = [VERSION_FILE, RELEASE_NOTES_FILE, README_FILE]
    if vi.ios_changed and vi.ios_new:
        files_to_stage.append(IOS_VERSION_FILE)
    if vi.sync_changed and vi.sync_new:
        files_to_stage.append(SYNC_VERSION_FILE)

    git(["add", *files_to_stage], write=True)
    commit_msg = f"Update version to {vi.release_version} for merge to main"
    git(["commit", "-m", commit_msg], write=True)
    ok(f"Committed: {commit_msg}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 4: Merge to main
# ══════════════════════════════════════════════════════════════════════════════


def step4_merge_to_main(vi: VersionInfo) -> None:
    """Checkout main and merge dev with --no-ff.  Handle conflicts interactively."""
    section("Step 4: Merge to main")

    git(["checkout", MAIN_BRANCH], write=True)
    ok(f"Switched to {MAIN_BRANCH}.")

    try:
        git(["merge", DEV_BRANCH, "--no-ff"], write=True)
        ok(f"Merged {DEV_BRANCH} → {MAIN_BRANCH}.")
    except subprocess.CalledProcessError as exc:
        if DRY_RUN:
            return
        stderr = exc.stderr or ""
        stdout = exc.output or ""
        if "conflict" in stderr.lower() or "conflict" in stdout.lower():
            _handle_merge_conflict()
        else:
            abort(f"Merge failed:\n{stderr.strip()}")

    if DRY_RUN:
        return

    head_version = read_porter_version()
    if head_version != vi.release_version:
        abort(
            f"VERSION mismatch after merge! "
            f"Expected {vi.release_version!r}, got {head_version!r}. "
            "Investigate before proceeding."
        )
    ok(f"Verified: VERSION = {vi.release_version} on {MAIN_BRANCH}.")


def _handle_merge_conflict() -> None:
    """Interactively guide the user through resolving a merge conflict."""
    conflicted = git(["diff", "--name-only", "--diff-filter=U"]).strip()
    err("Merge conflict! Conflicted files:")
    for f in conflicted.splitlines():
        print(f"  {C_RED}•{C_RESET} {f}")

    print(f"\n{C_BOLD}Options:{C_RESET}")
    print("  1. Abort merge and return to dev (default, recommended)")
    print("  2. Resolve manually in another terminal, then continue here")
    choice = ask("Choice", "1")

    if choice != "2":
        git(["merge", "--abort"], write=True)
        git(["checkout", DEV_BRANCH], write=True)
        warn(
            "Merge aborted and returned to dev.\n"
            "  The version commit remains on dev.\n"
            "  Resolve the conflict, then re-run this script."
        )
        sys.exit(1)

    print(f"\n{C_BOLD}Manual resolution steps:{C_RESET}")
    print("  1. Edit conflicted files to resolve conflicts")
    print("  2. Stage resolved files:   git add <file>")
    print("  3. Complete the merge:     git merge --continue")
    print("  4. Return here and press Enter")
    try:
        input("\nPress Enter when the merge is fully committed… ")
    except (KeyboardInterrupt, EOFError):
        print()
        abort("Aborted by user.")

    remaining = git(["diff", "--name-only", "--diff-filter=U"]).strip()
    if remaining:
        abort(f"Conflicts still unresolved:\n  {remaining}\nPlease finish resolving before continuing.")

    ok("Merge conflict resolved.")


# ══════════════════════════════════════════════════════════════════════════════
# Step 5: Tag and set next dev version
# ══════════════════════════════════════════════════════════════════════════════


def step5_tag_and_next_dev(vi: VersionInfo) -> None:
    """Create the release tag, merge back to dev, bump to next -dev version."""
    section("Step 5: Tag and Set Next Dev Version")

    tag_name = f"v{vi.release_version}"
    git(["tag", tag_name], write=True)
    ok(f"Created tag: {tag_name}")

    git(["checkout", DEV_BRANCH], write=True)
    ok(f"Switched to {DEV_BRANCH}.")

    git(["merge", MAIN_BRANCH], write=True)
    ok(f"Merged {MAIN_BRANCH} back into {DEV_BRANCH}.")

    # Set next dev version (no +hash — merge-to-dev appends it)
    write_porter_version(vi.next_dev)
    git(["add", VERSION_FILE], write=True)
    git(["commit", "-m", f"Set next dev version to {vi.next_dev}"], write=True)
    ok(f"Next dev version set: {vi.next_dev}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 6: Push, clean up, report
# ══════════════════════════════════════════════════════════════════════════════


def step6_push_and_cleanup(vi: VersionInfo) -> None:
    """Push to remote, delete merged branches, print release summary."""
    section("Step 6: Push and Clean Up")

    if has_remote():
        try:
            git(["push", "origin", MAIN_BRANCH, DEV_BRANCH, "--tags"], write=True)
            ok(f"Pushed {MAIN_BRANCH}, {DEV_BRANCH}, and tags to origin.")
        except subprocess.CalledProcessError as exc:
            warn(f"Push failed: {(exc.stderr or '').strip()}")
            warn("Local commits and tag are intact. Push manually when ready:")
            warn(f"  git push origin {MAIN_BRANCH} {DEV_BRANCH} --tags")
    else:
        warn("No remote 'origin' found — skipping push.")

    if DRY_RUN:
        dry(f"Delete branches merged into {DEV_BRANCH} (excluding {MAIN_BRANCH}/{DEV_BRANCH})")
    else:
        _delete_merged_branches()

    _print_final_report(vi)


def _delete_merged_branches() -> None:
    """Delete local branches that are fully merged into dev."""
    protected = {MAIN_BRANCH, DEV_BRANCH}
    merged_output = git(["branch", "--merged", DEV_BRANCH]).strip()
    deleted: list[str] = []
    for line in merged_output.splitlines():
        branch = line.strip().lstrip("* ")
        if branch and branch not in protected:
            try:
                git(["branch", "-d", branch])
                deleted.append(branch)
            except subprocess.CalledProcessError as exc:
                warn(f"Could not delete branch '{branch}': {(exc.stderr or '').strip()}")
    if deleted:
        ok(f"Deleted merged branches: {', '.join(deleted)}")
    else:
        ok("No merged branches to clean up.")


def _print_final_report(vi: VersionInfo) -> None:
    """Print the final release summary."""
    bar = "═" * 60
    print(f"\n{C_BOLD}{C_GREEN}{bar}{C_RESET}")
    print(f"{C_BOLD}{C_GREEN}  Release complete!{C_RESET}")
    print(f"{C_BOLD}{C_GREEN}{bar}{C_RESET}")
    print(f"  Tag:         v{vi.release_version}")
    print(f"  Dev version: {vi.next_dev}")
    if vi.ios_changed and vi.ios_new:
        print(f"  iOS:         {vi.ios_current} → {vi.ios_new}")
    if vi.sync_changed and vi.sync_new:
        print(f"  Sync client: {vi.sync_current} → {vi.sync_new}")
    print(f"\n{C_BOLD}Recent commits on {MAIN_BRANCH}:{C_RESET}")
    log = git(["log", MAIN_BRANCH, "--oneline", f"-{FINAL_LOG_COUNT}"]).strip()
    for line in log.splitlines():
        print(f"  {line}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Merge dev into main with version bump, tagging, and release workflow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  ./build/merge_dev_to_main-opus-planned.py           # full interactive workflow\n"
            "  ./build/merge_dev_to_main-opus-planned.py --dry-run # preview without changes\n"
            "  ./build/merge_dev_to_main-opus-planned.py --skip-srs # bypass SRS gate\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run read operations and prompts; print write operations without executing them.",
    )
    parser.add_argument(
        "--skip-srs",
        action="store_true",
        help="Bypass the SRS completeness gate (allow requirements with [ ] status).",
    )
    return parser.parse_args()


def verify_project_root() -> Path:
    """Walk up from cwd until porter_core.py and .git/ are both found."""
    candidate = Path.cwd()
    while True:
        if (candidate / "porter_core.py").exists() and (candidate / ".git").is_dir():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    err("Cannot locate project root (looking for porter_core.py + .git/).")
    err("Run this script from within the music-porter directory.")
    sys.exit(1)


def main() -> None:
    """Entry point: parse args, locate root, run all six steps."""
    global DRY_RUN, SKIP_SRS, PROJECT_ROOT

    args = parse_args()
    DRY_RUN = args.dry_run
    SKIP_SRS = args.skip_srs
    PROJECT_ROOT = verify_project_root()

    if DRY_RUN:
        print(f"{C_YELLOW}{C_BOLD}DRY-RUN mode — no changes will be made.{C_RESET}")

    print(f"\n{C_BOLD}music-porter: merge-dev-to-main{C_RESET}")
    print(f"Project root: {PROJECT_ROOT}")

    step1_verify_and_sync()
    vi = step2_determine_versions()
    step3_prepare_release(vi)
    step4_merge_to_main(vi)
    step5_tag_and_next_dev(vi)
    step6_push_and_cleanup(vi)


if __name__ == "__main__":
    main()
