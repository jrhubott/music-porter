#!/usr/bin/env python3
"""cut-release.py — Standalone release workflow for music-porter.

Replicates the /merge-dev-to-main skill workflow as an interactive CLI tool.
Run from the project root or any subdirectory of it.

Usage:
    ./build/cut-release.py [options]
    python3 build/cut-release.py [options]

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
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn

# ══════════════════════════════════════════════════════════════════════════════
# Constants — no magic literals in logic
# ══════════════════════════════════════════════════════════════════════════════

MAIN_BRANCH = "main"
DEV_BRANCH = "dev"
VERSION_FILE = "server/core/porter_core.py"
IOS_VERSION_FILE = "clients/ios/MusicPorter/MusicPorter/MusicPorterApp.swift"
SYNC_VERSION_FILE = "clients/sync-client/packages/core/src/constants.ts"
RELEASE_NOTES_FILE = "release-notes.txt"
README_FILE = "README.md"
SRS_GLOB = "SRS/*.md"
FINAL_LOG_COUNT = 5  # recent commits shown in final report
EDITOR_FALLBACK = "vi"

# Maps --bump choices and interactive numeric inputs to canonical bump types
BUMP_MAP: dict[str, str] = {
    "patch": "PATCH",
    "1": "PATCH",
    "minor": "MINOR",
    "2": "MINOR",
    "major": "MAJOR",
    "3": "MAJOR",
}

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
    "set dev version",
    "update version to",
    "merge branch",
    "merge remote-tracking",
)

# ANSI color/style codes — reassigned to "" by _init_colors() if NO_COLOR
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
NON_INTERACTIVE: bool = False
NO_COLOR: bool = False
QUIET: bool = False
AUTO_STASH: bool = False
NO_PUSH: bool = False
NO_DELETE_BRANCHES: bool = False
PROJECT_ROOT: Path = Path(".")
_STASH_ACTIVE: bool = False  # True while a cut-release auto-stash is live


# ══════════════════════════════════════════════════════════════════════════════
# Color initialization
# ══════════════════════════════════════════════════════════════════════════════


def _init_colors() -> None:
    """Disable ANSI codes when NO_COLOR is set or stdout is not a TTY."""
    global C_GREEN, C_RED, C_YELLOW, C_CYAN, C_BOLD, C_RESET
    if NO_COLOR:
        C_GREEN = C_RED = C_YELLOW = C_CYAN = C_BOLD = C_RESET = ""


# ══════════════════════════════════════════════════════════════════════════════
# Output helpers
# ══════════════════════════════════════════════════════════════════════════════


def ok(msg: str) -> None:
    """Print a success/info message (suppressed by --quiet)."""
    if not QUIET:
        print(f"{C_GREEN}✓{C_RESET} {msg}")


def warn(msg: str) -> None:
    """Print a warning to stderr (always shown, even with --quiet)."""
    print(f"{C_YELLOW}⚠{C_RESET}  {msg}", file=sys.stderr)


def err(msg: str) -> None:
    """Print an error to stderr."""
    print(f"{C_RED}✗{C_RESET} {msg}", file=sys.stderr)


def section(title: str) -> None:
    """Print a bold section header (suppressed by --quiet)."""
    if not QUIET:
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


def abort(msg: str) -> NoReturn:
    """Print an error message and exit with failure."""
    err(msg)
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# Stash management
# ══════════════════════════════════════════════════════════════════════════════


def _stash_push() -> None:
    """Create an auto-stash and mark it as active."""
    global _STASH_ACTIVE
    git(["stash", "push", "-u", "-m", "cut-release: auto-stash"], write=True)
    _STASH_ACTIVE = True
    ok("Changes stashed (will be popped when the script finishes).")


def _stash_pop() -> None:
    """Pop the auto-stash if one was created by this script."""
    global _STASH_ACTIVE
    if not _STASH_ACTIVE:
        return
    try:
        git(["stash", "pop"], write=True)
        ok("Stash popped.")
    except subprocess.CalledProcessError as exc:
        warn(f"Could not pop stash: {(exc.stderr or '').strip()}")
        warn("Run 'git stash pop' manually.")
    _STASH_ACTIVE = False


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
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                ["git", *args],
                output=result.stdout,
                stderr=result.stderr,
            )
        return result.stdout
    except FileNotFoundError:
        abort("git not found in PATH.")


def has_remote(name: str = "origin") -> bool:
    """Return True if the given remote exists."""
    return name in git(["remote"]).split()


# ══════════════════════════════════════════════════════════════════════════════
# Version helpers
# ══════════════════════════════════════════════════════════════════════════════


def semver_parts(version: str) -> tuple[int, int, int]:
    """Extract (major, minor, patch) integers from a semver string."""
    m = RE_SEMVER.match(version)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    abort(f"Cannot parse semver from: {version!r}")


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
    if m:
        return m.group(0)
    abort(f"Cannot parse base version from: {version!r}")


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
    if m:
        return m.group(1)
    abort(f"Cannot find VERSION in {VERSION_FILE}.")


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
    if m:
        return m.group(1)
    abort(f"Cannot find appVersion in {IOS_VERSION_FILE}.")


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
    if m:
        return m.group(1)
    abort(f"Cannot find VERSION in {SYNC_VERSION_FILE}.")


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
    log_range = f"{last_tag}..{DEV_BRANCH}" if last_tag else DEV_BRANCH
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


def process_readme_features(version: str, args: argparse.Namespace) -> None:
    """Mark Future Features as implemented, driven by --strike-features or interactively."""
    readme_path = PROJECT_ROOT / README_FILE
    if not readme_path.exists():
        warn(f"{README_FILE} not found — skipping feature strikethrough.")
        return

    readme_text = readme_path.read_text()
    features = find_unimplemented_features(readme_text)

    if not features:
        ok("No un-struck Future Features in README.")
        return

    selected: list[int] = []

    if args.strike_features is not None:
        # Pre-answered via --strike-features 1,3,5
        for part in args.strike_features.split(","):
            part = part.strip()
            if part.isdigit():
                n = int(part)
                if 1 <= n <= len(features):
                    selected.append(n - 1)
        if not selected:
            ok("No valid feature numbers in --strike-features — skipping strikethrough.")
            return
    elif NON_INTERACTIVE:
        ok("No --strike-features provided in non-interactive mode — skipping strikethrough.")
        return
    else:
        print(f"\n{C_BOLD}Unimplemented Future Features:{C_RESET}")
        for i, (_, line) in enumerate(features, 1):
            print(f"  {i:2d}. {line.strip()}")

        print()
        raw = ask(
            "Numbers to mark as implemented in this release (comma-separated, or Enter to skip)"
        )
        if not raw.strip():
            ok("No features marked as implemented.")
            return

        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                n = int(part)
                if 1 <= n <= len(features):
                    selected.append(n - 1)

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
# SRS gate — with interactive recovery menu
# ══════════════════════════════════════════════════════════════════════════════


def check_srs_gate() -> None:
    """Scan SRS/*.md for unchecked client columns.

    In interactive mode, offers recovery options on failure.
    In non-interactive mode, exits immediately unless --skip-srs is set.
    """
    if SKIP_SRS:
        warn("SRS completeness gate bypassed via --skip-srs.")
        return

    srs_files = sorted(glob.glob(str(PROJECT_ROOT / SRS_GLOB)))
    if not srs_files:
        ok("No SRS files found — gate passed.")
        return

    while True:
        incomplete: list[str] = []
        for srs_file in srs_files:
            path = Path(srs_file)
            for line_num, line in enumerate(path.read_text().splitlines(), 1):
                if RE_SRS_UNCHECKED.search(line):
                    incomplete.append(f"  {path.name}:{line_num}: {line.strip()}")

        if not incomplete:
            ok("SRS gate passed — all requirements are implemented.")
            return

        err(f"SRS gate FAILED — {len(incomplete)} incomplete requirement(s):")
        for item in incomplete:
            print(item, file=sys.stderr)

        if NON_INTERACTIVE:
            err("Use --skip-srs to bypass the SRS gate in non-interactive mode.")
            sys.exit(1)

        print(f"\n{C_BOLD}Options:{C_RESET}")
        print("  1. Open SRS files for review, re-check after Enter")
        print("  2. Skip the gate and continue")
        print("  3. Abort")
        choice = ask("Choice", "3")

        if choice == "1":
            editor = os.environ.get("EDITOR", os.environ.get("VISUAL", EDITOR_FALLBACK))
            try:
                subprocess.run([editor, *srs_files], check=False)
            except FileNotFoundError:
                warn(f"Editor '{editor}' not found.")
            try:
                input("\nPress Enter to re-check SRS… ")
            except (KeyboardInterrupt, EOFError):
                print()
                sys.exit(1)
            # Loop back to re-check
        elif choice == "2":
            warn("SRS gate bypassed by user choice.")
            return
        else:
            sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# Remote branch sync helpers — with diverge recovery menu
# ══════════════════════════════════════════════════════════════════════════════


def sync_branch_from_remote(branch: str) -> None:
    """Fast-forward local branch from remote if behind.

    Shows an interactive recovery menu if branches have truly diverged.
    In non-interactive mode, exits immediately on diverge.
    """
    try:
        local_sha = git(["rev-parse", branch]).strip()
        remote_sha = git(["rev-parse", f"origin/{branch}"]).strip()
    except subprocess.CalledProcessError:
        # Remote doesn't track this branch — nothing to sync
        return

    if local_sha == remote_sha:
        ok(f"{branch} is up to date with remote.")
        return

    # Is local an ancestor of remote? If so, we can fast-forward.
    ff_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", local_sha, remote_sha],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    if ff_check.returncode == 0:
        git(["fetch", "origin", f"{branch}:{branch}"], write=True)
        ok(f"Fast-forwarded {branch} from remote.")
        return

    # Is remote an ancestor of local? Local is ahead — nothing to do.
    ahead_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", remote_sha, local_sha],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    if ahead_check.returncode == 0:
        ok(f"{branch} is ahead of remote — no update needed.")
        return

    # True diverge: neither is an ancestor of the other
    _recover_diverged(branch, local_sha, remote_sha)


def _recover_diverged(branch: str, local_sha: str, remote_sha: str) -> None:
    """Show diverge recovery menu.  Exits unless user explicitly chooses to continue."""
    try:
        local_ahead = git(
            ["rev-list", "--count", f"origin/{branch}..{branch}"]
        ).strip()
        remote_ahead = git(
            ["rev-list", "--count", f"{branch}..origin/{branch}"]
        ).strip()
    except subprocess.CalledProcessError:
        local_ahead = remote_ahead = "?"

    err(f"{branch} has diverged from origin/{branch}.")
    print(f"  Local:  {local_sha[:8]} ({local_ahead} commit(s) ahead of remote)")
    print(f"  Remote: {remote_sha[:8]} ({remote_ahead} commit(s) ahead of local)")

    if NON_INTERACTIVE:
        err("Diverged branches require manual reconciliation. Aborting.")
        sys.exit(1)

    print(f"\n{C_BOLD}Options:{C_RESET}")
    print("  1. Show diverging commits then abort  (recommended)")
    print("  2. Abort")
    print("  3. Continue anyway  (dangerous — requires typing YES)")
    choice = ask("Choice", "1")

    if choice == "1":
        print(f"\n{C_BOLD}Commits on {branch} not on origin/{branch}:{C_RESET}")
        local_log = git(["log", f"origin/{branch}..{branch}", "--oneline"]).strip()
        for line in (local_log.splitlines() if local_log else ["(none)"]):
            print(f"  {C_YELLOW}{line}{C_RESET}")
        print(f"\n{C_BOLD}Commits on origin/{branch} not on {branch}:{C_RESET}")
        remote_log = git(["log", f"{branch}..origin/{branch}", "--oneline"]).strip()
        for line in (remote_log.splitlines() if remote_log else ["(none)"]):
            print(f"  {C_YELLOW}{line}{C_RESET}")
        sys.exit(1)
    elif choice == "3":
        confirm_text = ask(
            "Type YES to confirm continuing despite diverged branches"
        )
        if confirm_text != "YES":
            sys.exit(1)
        warn(
            f"Continuing despite {branch} diverged from origin/{branch} — "
            "proceed with caution."
        )
    else:
        sys.exit(1)


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
    srs_skipped: bool  # True if SRS gate was bypassed


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: Verify and sync
# ══════════════════════════════════════════════════════════════════════════════


def step1_verify_and_sync(*, allow_no_commits: bool = False) -> str:
    """Switch to dev, verify clean tree, sync from remote, display commit log."""
    section("Step 1: Verify and Sync")

    current = git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if current != DEV_BRANCH:
        ok(f"Switching from '{current}' to '{DEV_BRANCH}'…")
        git(["checkout", DEV_BRANCH], write=True)

    # Dirty tree check — loop until clean or stashed
    while True:
        status = git(["status", "--porcelain"]).strip()
        if not status:
            ok("Working tree is clean.")
            break

        err("Working tree is not clean:")
        for line in status.splitlines():
            print(f"  {line}")

        if NON_INTERACTIVE:
            if AUTO_STASH:
                _stash_push()
                break
            err(
                "Working tree is dirty. "
                "Use --auto-stash to stash automatically in non-interactive mode."
            )
            sys.exit(1)

        if AUTO_STASH:
            _stash_push()
            break

        print(f"\n{C_BOLD}Options:{C_RESET}")
        print("  1. Stash changes and continue  (git stash — popped at end)")
        print("  2. I'll clean up — press Enter to retry")
        print("  3. Abort")
        choice = ask("Choice", "1")

        if choice == "1":
            _stash_push()
            break
        elif choice == "2":
            try:
                input("Clean up, then press Enter to retry… ")
            except (KeyboardInterrupt, EOFError):
                print()
                sys.exit(1)
            # Loop to re-check
        else:
            sys.exit(1)

    if has_remote():
        ok("Fetching from origin…")
        git(["fetch", "origin"], write=True)
        sync_branch_from_remote(MAIN_BRANCH)
        sync_branch_from_remote(DEV_BRANCH)
    else:
        warn("No remote 'origin' found — skipping fetch and sync.")

    commit_log = git(["log", f"{MAIN_BRANCH}..{DEV_BRANCH}", "--oneline"]).strip()
    if not commit_log:
        dev_sha = git(["rev-parse", "--short", DEV_BRANCH]).strip()
        main_sha = git(["rev-parse", "--short", MAIN_BRANCH]).strip()
        err("No commits on dev ahead of main.")
        print(f"  {DEV_BRANCH} HEAD:  {dev_sha}")
        print(f"  {MAIN_BRANCH} HEAD: {main_sha}")

        if allow_no_commits:
            warn("Continuing despite no new commits (--allow-no-commits).")
        elif NON_INTERACTIVE:
            err("No commits to merge. Use --allow-no-commits to override.")
            sys.exit(1)
        else:
            print(f"\n{C_BOLD}Options:{C_RESET}")
            print(f"  1. Show recent commits on {DEV_BRANCH} and {MAIN_BRANCH}")
            print("  2. Continue anyway  (only if re-running after a push failure)")
            print("  3. Abort")
            choice = ask("Choice", "3")

            if choice == "1":
                print(f"\n{C_BOLD}Recent commits on {DEV_BRANCH}:{C_RESET}")
                for line in git(
                    ["log", DEV_BRANCH, "--oneline", f"-{FINAL_LOG_COUNT}"]
                ).strip().splitlines():
                    print(f"  {line}")
                print(f"\n{C_BOLD}Recent commits on {MAIN_BRANCH}:{C_RESET}")
                for line in git(
                    ["log", MAIN_BRANCH, "--oneline", f"-{FINAL_LOG_COUNT}"]
                ).strip().splitlines():
                    print(f"  {line}")
                sys.exit(1)
            elif choice == "2":
                warn("Continuing with no new commits (re-run mode).")
            else:
                sys.exit(1)

    if commit_log:
        print(f"\n{C_BOLD}Commits to merge ({DEV_BRANCH} → {MAIN_BRANCH}):{C_RESET}")
        for line in commit_log.splitlines():
            print(f"  {line}")

    return commit_log


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: Determine versions
# ══════════════════════════════════════════════════════════════════════════════


def step2_determine_versions(args: argparse.Namespace) -> VersionInfo:
    """Read current versions, detect component changes, resolve bump decisions."""
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

    ios_files = git(["diff", diff_ref, "--name-only", "--", "clients/ios/"]).strip()
    ios_changed = bool(ios_files)
    ios_current = read_ios_version()
    if ios_changed:
        ok(
            f"iOS changes detected since {last_tag or 'beginning'} "
            f"(current: {ios_current})"
        )
    else:
        ok(f"No iOS changes since {last_tag or 'beginning'}.")

    sync_files = git(["diff", diff_ref, "--name-only", "--", "clients/sync-client/"]).strip()
    sync_changed = bool(sync_files)
    sync_current = read_sync_version()
    if sync_changed:
        ok(
            f"Sync-client changes detected since {last_tag or 'beginning'} "
            f"(current: {sync_current})"
        )
    else:
        ok(f"No sync-client changes since {last_tag or 'beginning'}.")

    # ── Server version bump ──────────────────────────────────────────────────
    if args.bump:
        bump_type = BUMP_MAP[args.bump]  # guaranteed valid (argparse choices)
        ok(f"Server bump type: {bump_type} (from --bump)")
    elif NON_INTERACTIVE:
        err("--non-interactive requires --bump {patch,minor,major}.")
        sys.exit(1)
    else:
        print(f"\n{C_BOLD}Server version bump{C_RESET} (current base: {base_version})")
        print("  1. PATCH (default) — bug fixes and minor improvements")
        print("  2. MINOR — new features, backwards compatible")
        print("  3. MAJOR — breaking changes")
        choice = ask("Bump type", "1")
        bump_type = BUMP_MAP.get(choice.lower(), "PATCH")

    release_version = apply_bump(base_version, bump_type)
    ok(f"Release version: {release_version} ({bump_type} bump)")
    next_dev = next_dev_version(release_version)

    # ── iOS version ──────────────────────────────────────────────────────────
    ios_new = ""
    if args.no_ios_bump:
        if ios_changed:
            warn(
                "iOS changes detected but --no-ios-bump is set — "
                "skipping iOS version bump."
            )
    elif ios_changed or args.ios_version:
        if args.ios_version:
            ios_new = args.ios_version
            ok(f"iOS: {ios_current} → {ios_new} (from --ios-version)")
        elif NON_INTERACTIVE:
            err(
                "iOS changes detected but neither --ios-version nor --no-ios-bump "
                "was provided."
            )
            sys.exit(1)
        else:
            suggested = patch_bump(ios_current)
            print(
                f"\n{C_BOLD}iOS version{C_RESET}: current = {ios_current}, "
                f"suggested = {suggested}"
            )
            ios_new = ask("New iOS appVersion", suggested)
            ok(f"iOS: {ios_current} → {ios_new}")

    # ── Sync-client version ──────────────────────────────────────────────────
    sync_new = ""
    if args.no_sync_bump:
        if sync_changed:
            warn(
                "Sync-client changes detected but --no-sync-bump is set — "
                "skipping sync version bump."
            )
    elif sync_changed or args.sync_version:
        if args.sync_version:
            sync_new = args.sync_version
            ok(f"Sync-client: {sync_current} → {sync_new} (from --sync-version)")
        elif NON_INTERACTIVE:
            err(
                "Sync-client changes detected but neither --sync-version nor "
                "--no-sync-bump was provided."
            )
            sys.exit(1)
        else:
            suggested = patch_bump(sync_current)
            print(
                f"\n{C_BOLD}Sync-client version{C_RESET}: current = {sync_current}, "
                f"suggested = {suggested}"
            )
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
        srs_skipped=SKIP_SRS,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Step 3: Prepare release on dev
# ══════════════════════════════════════════════════════════════════════════════


def step3_prepare_release(vi: VersionInfo, args: argparse.Namespace) -> None:
    """SRS gate, README, release notes, version files, release commit on dev."""
    section("Step 3: Prepare Release on dev")

    check_srs_gate()

    if args.no_readme_update:
        ok("README Future Features update skipped (--no-readme-update).")
    else:
        process_readme_features(vi.release_version, args)

    # ── Release notes ────────────────────────────────────────────────────────
    if args.release_notes_from:
        notes_path = Path(args.release_notes_from)
        if not notes_path.exists():
            abort(f"--release-notes-from file not found: {notes_path}")
        draft = notes_path.read_text()
        ok(f"Release notes loaded from {notes_path}")
    else:
        draft = build_release_notes_draft(vi.release_version, vi.last_tag)

        # Append bullets from --release-notes-append
        if args.release_notes_append:
            extra_bullets = "\n".join(
                f"• {line}" for line in args.release_notes_append
            )
            draft = draft.rstrip("\n") + "\n" + extra_bullets + "\n"

        # Append component version bump bullets
        component_notes: list[str] = []
        if vi.ios_changed and vi.ios_new:
            component_notes.append(f"• iOS companion app updated to v{vi.ios_new}")
        if vi.sync_changed and vi.sync_new:
            component_notes.append(f"• Sync client updated to v{vi.sync_new}")
        if component_notes:
            draft = draft.rstrip("\n") + "\n" + "\n".join(component_notes) + "\n"

        print(f"\n{C_BOLD}Draft release notes:{C_RESET}")
        print(draft)

        if not args.no_editor and not NON_INTERACTIVE:
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
        _recover_version_mismatch(vi.release_version, head_version)
    else:
        ok(f"Verified: VERSION = {vi.release_version} on {MAIN_BRANCH}.")


def _handle_merge_conflict() -> None:
    """Interactively guide the user through resolving a merge conflict."""
    conflicted = git(["diff", "--name-only", "--diff-filter=U"]).strip()
    err("Merge conflict! Conflicted files:")
    for f in conflicted.splitlines():
        print(f"  {C_RED}•{C_RESET} {f}")

    if NON_INTERACTIVE:
        err("Merge conflict in non-interactive mode — aborting.")
        git(["merge", "--abort"], write=True)
        git(["checkout", DEV_BRANCH], write=True)
        sys.exit(1)

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
        abort(
            f"Conflicts still unresolved:\n  {remaining}\n"
            "Please finish resolving before continuing."
        )
    ok("Merge conflict resolved.")


def _recover_version_mismatch(expected: str, got: str) -> None:
    """Show VERSION mismatch recovery menu after merging to main."""
    err(f"VERSION mismatch after merge! Expected {expected!r}, got {got!r}.")

    if NON_INTERACTIVE:
        err("Mismatch in non-interactive mode — aborting. Investigate manually.")
        sys.exit(1)

    print(f"\n{C_BOLD}Options:{C_RESET}")
    print("  1. Show git diff and abort  (recommended)")
    print("  2. Fix manually then press Enter to re-verify")
    print("  3. Accept mismatch and continue  (dangerous — requires typing YES)")
    choice = ask("Choice", "1")

    if choice == "1":
        diff = git(["diff", "HEAD~1", "HEAD", "--", VERSION_FILE]).strip()
        if diff:
            print(f"\n{C_BOLD}VERSION diff:{C_RESET}")
            for line in diff.splitlines():
                print(f"  {line}")
        sys.exit(1)
    elif choice == "2":
        try:
            input("Fix the VERSION, stage the change, and press Enter to re-verify… ")
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(1)
        current = read_porter_version()
        if current != expected:
            err(f"VERSION is still {current!r}, expected {expected!r}. Aborting.")
            sys.exit(1)
        ok(f"VERSION re-verified: {current}")
    elif choice == "3":
        confirm_text = ask("Type YES to accept the mismatch and continue")
        if confirm_text != "YES":
            sys.exit(1)
        warn(f"Continuing with VERSION mismatch ({got!r} instead of {expected!r}).")
    else:
        sys.exit(1)


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


def step6_push_and_cleanup(vi: VersionInfo, args: argparse.Namespace) -> None:
    """Push to remote, delete merged branches, print release summary."""
    section("Step 6: Push and Clean Up")

    if args.no_push:
        warn("Remote push skipped (--no-push). Push manually when ready:")
        warn(f"  git push origin {MAIN_BRANCH} {DEV_BRANCH} --tags")
    elif has_remote():
        try:
            git(["push", "origin", MAIN_BRANCH, DEV_BRANCH, "--tags"], write=True)
            ok(f"Pushed {MAIN_BRANCH}, {DEV_BRANCH}, and tags to origin.")
        except subprocess.CalledProcessError as exc:
            warn(f"Push failed: {(exc.stderr or '').strip()}")
            warn("Local commits and tag are intact. Push manually when ready:")
            warn(f"  git push origin {MAIN_BRANCH} {DEV_BRANCH} --tags")
    else:
        warn("No remote 'origin' found — skipping push.")

    if args.no_delete_branches:
        ok("Branch cleanup skipped (--no-delete-branches).")
    elif DRY_RUN:
        dry(
            f"Delete branches merged into {DEV_BRANCH} "
            f"(excluding {MAIN_BRANCH}/{DEV_BRANCH})"
        )
    else:
        _delete_merged_branches()

    _print_final_report(vi)

    if args.output_json:
        result = {
            "tag": f"v{vi.release_version}",
            "release_version": vi.release_version,
            "next_dev": vi.next_dev,
            "ios_version": vi.ios_new or vi.ios_current,
            "sync_version": vi.sync_new or vi.sync_current,
            "srs_skipped": vi.srs_skipped,
        }
        print(json.dumps(result))


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
                warn(
                    f"Could not delete branch '{branch}': "
                    f"{(exc.stderr or '').strip()}"
                )
    if deleted:
        ok(f"Deleted merged branches: {', '.join(deleted)}")
    else:
        ok("No merged branches to clean up.")


def _print_final_report(vi: VersionInfo) -> None:
    """Print the final release summary (suppressed by --quiet)."""
    if QUIET:
        return
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
    if vi.srs_skipped:
        print(f"  {C_YELLOW}⚠  SRS gate was bypassed{C_RESET}")
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
        prog="cut-release.py",
        description="Cut a music-porter release: version bump, tagging, and merge workflow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  ./build/cut-release.py                        # full interactive workflow\n"
            "  ./build/cut-release.py --dry-run              # preview without changes\n"
            "  ./build/cut-release.py --skip-srs             # bypass SRS gate\n"
            "  ./build/cut-release.py --non-interactive \\\n"
            "      --bump patch --no-ios-bump --no-sync-bump \\\n"
            "      --no-editor --no-readme-update --skip-srs  # CI/automated\n"
        ),
    )

    # ── Existing flags ────────────────────────────────────────────────────────
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

    # ── Version bump flags ────────────────────────────────────────────────────
    bump_group = parser.add_argument_group("version bump")
    bump_group.add_argument(
        "--bump",
        choices=["patch", "minor", "major"],
        metavar="{patch,minor,major}",
        help="Pre-answer the server version bump type (skips the interactive prompt).",
    )
    bump_group.add_argument(
        "--ios-version",
        metavar="X.Y.Z",
        help="Pre-answer the iOS appVersion (e.g. 1.6.2).",
    )
    bump_group.add_argument(
        "--sync-version",
        metavar="X.Y.Z",
        help="Pre-answer the sync-client VERSION (e.g. 1.6.2).",
    )
    bump_group.add_argument(
        "--no-ios-bump",
        action="store_true",
        help="Suppress iOS version bump even if iOS changes are detected.",
    )
    bump_group.add_argument(
        "--no-sync-bump",
        action="store_true",
        help="Suppress sync-client version bump even if sync-client changes are detected.",
    )

    # ── Release notes flags ───────────────────────────────────────────────────
    notes_group = parser.add_argument_group("release notes")
    notes_group.add_argument(
        "--no-editor",
        action="store_true",
        help='Skip the "open in $EDITOR to refine?" prompt.',
    )
    notes_group.add_argument(
        "--release-notes-from",
        metavar="FILE",
        help="Read release notes from FILE (skips auto-generation and editor).",
    )
    notes_group.add_argument(
        "--release-notes-append",
        metavar="TEXT",
        action="append",
        help="Append an extra bullet to the auto-generated draft (repeatable).",
    )

    # ── README flags ──────────────────────────────────────────────────────────
    readme_group = parser.add_argument_group("README")
    readme_group.add_argument(
        "--strike-features",
        metavar="N[,N,...]",
        help="Pre-answer Future Features strikethrough selection (comma-separated numbers).",
    )
    readme_group.add_argument(
        "--no-readme-update",
        action="store_true",
        help="Skip the Future Features strikethrough step entirely.",
    )

    # ── Merge / push flags ────────────────────────────────────────────────────
    push_group = parser.add_argument_group("merge and push")
    push_group.add_argument(
        "--no-push",
        action="store_true",
        help="Complete all local steps but skip the remote push.",
    )
    push_group.add_argument(
        "--no-delete-branches",
        action="store_true",
        help="Skip merged branch cleanup after the release.",
    )

    # ── Stash / recovery flags ────────────────────────────────────────────────
    recovery_group = parser.add_argument_group("stash and recovery")
    recovery_group.add_argument(
        "--auto-stash",
        action="store_true",
        help="Auto-stash dirty changes before proceeding; auto-pop at the end.",
    )
    recovery_group.add_argument(
        "--allow-no-commits",
        action="store_true",
        help="Continue even when dev has no new commits ahead of main (re-run mode).",
    )

    # ── CI / output flags ─────────────────────────────────────────────────────
    ci_group = parser.add_argument_group("CI and output")
    ci_group.add_argument(
        "--non-interactive",
        action="store_true",
        help=(
            "Master switch: disable all prompts. Any required-but-unflagged decision "
            "aborts with a clear error. Validated before Step 1 — no git ops run first."
        ),
    )
    ci_group.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color codes (also auto-detected when stdout is not a TTY).",
    )
    ci_group.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress ok/info/section output; errors and warnings still go to stderr.",
    )
    ci_group.add_argument(
        "--output-json",
        action="store_true",
        help=(
            "Write a machine-readable JSON summary to stdout on success: "
            "{tag, release_version, next_dev, ios_version, sync_version, srs_skipped}."
        ),
    )

    return parser.parse_args()


def verify_project_root() -> Path:
    """Walk up from cwd until server/core/porter_core.py and .git/ are both found."""
    candidate = Path.cwd()
    while True:
        if (candidate / "server" / "core" / "porter_core.py").exists() and (candidate / ".git").is_dir():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    err("Cannot locate project root (looking for server/core/porter_core.py + .git/).")
    err("Run this script from within the music-porter directory.")
    sys.exit(1)


def main() -> None:
    """Entry point: parse args, locate root, run all six steps."""
    global DRY_RUN, SKIP_SRS, NON_INTERACTIVE, NO_COLOR, QUIET
    global AUTO_STASH, NO_PUSH, NO_DELETE_BRANCHES, PROJECT_ROOT

    args = parse_args()
    DRY_RUN = args.dry_run
    SKIP_SRS = args.skip_srs
    NON_INTERACTIVE = args.non_interactive
    NO_COLOR = args.no_color or not sys.stdout.isatty()
    QUIET = args.quiet
    AUTO_STASH = args.auto_stash
    NO_PUSH = args.no_push
    NO_DELETE_BRANCHES = args.no_delete_branches
    PROJECT_ROOT = verify_project_root()

    _init_colors()

    # Validate --non-interactive requirements before running any git ops
    if NON_INTERACTIVE and args.bump is None:
        err("--non-interactive requires --bump {patch,minor,major}.")
        sys.exit(1)

    if DRY_RUN:
        print(f"{C_YELLOW}{C_BOLD}DRY-RUN mode — no changes will be made.{C_RESET}")
    if NON_INTERACTIVE:
        print(
            f"{C_YELLOW}{C_BOLD}NON-INTERACTIVE mode — all prompts suppressed.{C_RESET}",
            file=sys.stderr,
        )

    if not QUIET:
        print(f"\n{C_BOLD}music-porter: cut-release{C_RESET}")
        print(f"Project root: {PROJECT_ROOT}")

    try:
        step1_verify_and_sync(allow_no_commits=args.allow_no_commits)
        vi = step2_determine_versions(args)
        step3_prepare_release(vi, args)
        step4_merge_to_main(vi)
        step5_tag_and_next_dev(vi)
        step6_push_and_cleanup(vi, args)
    finally:
        _stash_pop()


if __name__ == "__main__":
    main()
