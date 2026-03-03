#!/usr/bin/env python3
"""merge-to-dev.py — Merge a feature branch into dev.

Replicates the /merge-to-dev skill workflow as a standalone CLI tool.
Run from the project root or any subdirectory of it.

Usage:
    ./build/merge-to-dev.py [options]
    python3 build/merge-to-dev.py [options]

Steps:
    1. Verify and sync  — branch check, clean tree, fetch, show commit log
    2. Merge into dev   — checkout dev, merge --no-ff, conflict handling
    3. Restore version  — set VERSION to X.Y.Z-dev+<hash>, commit
    4. Push and report  — push to origin, show log, branch switch prompt
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

# ══════════════════════════════════════════════════════════════════════════════
# Constants — no magic literals in logic
# ══════════════════════════════════════════════════════════════════════════════

DEV_BRANCH = "dev"
PROTECTED_BRANCHES = ("dev", "main")
VERSION_FILE = "porter_core.py"
FINAL_LOG_COUNT = 5  # recent commits shown in final report

# Regex patterns for locating version strings in source files
RE_PORTER_VERSION = re.compile(r'(VERSION\s*=\s*")[^"]+(")', re.MULTILINE)
RE_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)")

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
NON_INTERACTIVE: bool = False
NO_COLOR: bool = False
QUIET: bool = False
AUTO_STASH: bool = False
NO_PUSH: bool = False
PROJECT_ROOT: Path = Path(".")
_STASH_ACTIVE: bool = False  # True while an auto-stash is live


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
    git(["stash", "push", "-u", "-m", "merge-to-dev: auto-stash"], write=True)
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


def read_porter_version() -> str:
    """Read the raw VERSION value from porter_core.py (includes any suffix)."""
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


def strip_dev_suffix(version: str) -> str:
    """Strip any '-dev+hash' or '-branchname' suffix and return bare semver."""
    m = RE_SEMVER.match(version)
    if m:
        return m.group(0)
    abort(f"Cannot parse base version from: {version!r}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: Verify and sync
# ══════════════════════════════════════════════════════════════════════════════


def step1_verify_and_sync() -> str:
    """Verify on feature branch, check clean tree, sync remote, show log.

    Returns the feature branch name to merge.
    """
    section("Step 1: Verify and Sync")

    feature_branch = git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if feature_branch in PROTECTED_BRANCHES:
        abort(
            f"Current branch is '{feature_branch}'. "
            "Run this script from a feature or bugfix branch, not dev or main."
        )
    ok(f"On branch '{feature_branch}'.")

    # Dirty tree check
    status = git(["status", "--porcelain"]).strip()
    if status:
        err("Working tree is not clean:")
        for line in status.splitlines():
            print(f"  {line}", file=sys.stderr)

        if NON_INTERACTIVE:
            if AUTO_STASH:
                _stash_push()
            else:
                abort(
                    "Working tree is dirty. "
                    "Use --auto-stash to stash automatically in non-interactive mode."
                )
        elif AUTO_STASH:
            _stash_push()
        else:
            abort(
                "Working tree is dirty. "
                "Clean up your changes or use --auto-stash before merging."
            )
    else:
        ok("Working tree is clean.")

    # Remote sync
    if has_remote():
        try:
            git(["fetch", "origin"])
            ok("Fetched from origin.")
        except subprocess.CalledProcessError:
            warn("git fetch failed — continuing with local state.")

        # Fast-forward dev if behind remote
        try:
            local_sha = git(["rev-parse", DEV_BRANCH]).strip()
            remote_sha = git(["rev-parse", f"origin/{DEV_BRANCH}"]).strip()
        except subprocess.CalledProcessError:
            local_sha = remote_sha = ""

        if local_sha and remote_sha and local_sha != remote_sha:
            ff_check = subprocess.run(
                ["git", "merge-base", "--is-ancestor", local_sha, remote_sha],
                capture_output=True,
                cwd=str(PROJECT_ROOT),
            )
            if ff_check.returncode == 0:
                # Local dev is behind remote — fast-forward it
                git(["checkout", DEV_BRANCH], write=True)
                git(["pull", "origin", DEV_BRANCH], write=True)
                git(["checkout", feature_branch], write=True)
                ok(f"Fast-forwarded {DEV_BRANCH} from remote.")
            else:
                # Check if dev has diverged
                ahead_check = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", remote_sha, local_sha],
                    capture_output=True,
                    cwd=str(PROJECT_ROOT),
                )
                if ahead_check.returncode != 0:
                    # True diverge
                    try:
                        local_ahead = git(
                            ["rev-list", "--count", f"origin/{DEV_BRANCH}..{DEV_BRANCH}"]
                        ).strip()
                        remote_ahead = git(
                            ["rev-list", "--count", f"{DEV_BRANCH}..origin/{DEV_BRANCH}"]
                        ).strip()
                    except subprocess.CalledProcessError:
                        local_ahead = remote_ahead = "?"

                    err(f"{DEV_BRANCH} has diverged from origin/{DEV_BRANCH}.")
                    print(
                        f"  Local:  {local_sha[:8]} ({local_ahead} commit(s) ahead of remote)",
                        file=sys.stderr,
                    )
                    print(
                        f"  Remote: {remote_sha[:8]} ({remote_ahead} commit(s) ahead of local)",
                        file=sys.stderr,
                    )
                    abort(
                        f"Resolve the divergence manually "
                        f"(e.g. 'git checkout {DEV_BRANCH} && git pull --rebase') then retry."
                    )
                else:
                    ok(f"{DEV_BRANCH} is ahead of remote — no update needed.")
        elif local_sha == remote_sha and local_sha:
            ok(f"{DEV_BRANCH} is up to date with remote.")
    else:
        warn("No remote 'origin' configured — skipping fetch.")

    # Show commits to be merged
    log = git(["log", f"{DEV_BRANCH}..HEAD", "--oneline"]).strip()
    if log:
        print(f"\n{C_BOLD}Commits to merge into {DEV_BRANCH}:{C_RESET}")
        for line in log.splitlines():
            print(f"  {C_CYAN}{line}{C_RESET}")
    else:
        warn(f"No commits on '{feature_branch}' ahead of {DEV_BRANCH}.")

    return feature_branch


# ══════════════════════════════════════════════════════════════════════════════
# Step 2: Merge into dev
# ══════════════════════════════════════════════════════════════════════════════


def step2_merge(feature_branch: str) -> str:
    """Checkout dev and merge the feature branch with --no-ff.

    Returns the merge commit hash.
    On conflict: aborts, returns to feature branch, exits non-zero.
    """
    section("Step 2: Merge into dev")

    git(["checkout", DEV_BRANCH], write=True)
    ok(f"Switched to {DEV_BRANCH}.")

    try:
        git(["merge", feature_branch, "--no-ff"], write=True)
    except subprocess.CalledProcessError:
        # Conflict — collect conflicted files, abort, and return to feature branch
        conflicted = git(["diff", "--name-only", "--diff-filter=U"], check=False).strip()
        err("Merge conflict detected. Aborting merge.")
        if conflicted:
            print("Conflicted files:", file=sys.stderr)
            for f in conflicted.splitlines():
                print(f"  {f}", file=sys.stderr)

        try:
            git(["merge", "--abort"], write=True)
            git(["checkout", feature_branch], write=True)
        except subprocess.CalledProcessError:
            warn("Could not cleanly abort — check git status.")

        err(
            f"Resolve the conflicts on '{feature_branch}', then re-run this script."
        )
        sys.exit(1)

    merge_commit = git(["rev-parse", "--short", "HEAD"]).strip()
    ok(f"Merged '{feature_branch}' into {DEV_BRANCH} (commit {merge_commit}).")
    return merge_commit


# ══════════════════════════════════════════════════════════════════════════════
# Step 3: Restore dev version
# ══════════════════════════════════════════════════════════════════════════════


def step3_restore_version(merge_commit: str) -> str:
    """Set VERSION to X.Y.Z-dev+<hash> and commit.

    Returns the new dev version string.
    """
    section("Step 3: Restore Dev Version")

    current_version = read_porter_version()
    base_version = strip_dev_suffix(current_version)
    dev_version = f"{base_version}-dev+{merge_commit}"

    write_porter_version(dev_version)

    git(["add", VERSION_FILE], write=True)
    git(
        ["commit", "-m", f"Set dev version to {dev_version}"],
        write=True,
    )
    ok(f"Committed: Set dev version to {dev_version}")
    return dev_version


# ══════════════════════════════════════════════════════════════════════════════
# Step 4: Push and report
# ══════════════════════════════════════════════════════════════════════════════


def step4_push_and_report(
    feature_branch: str,
    merge_commit: str,
    dev_version: str,
    args: argparse.Namespace,
) -> None:
    """Push dev to origin, print confirmation log, prompt for branch switch."""
    section("Step 4: Push and Report")

    if NO_PUSH:
        warn(f"Skipping push (--no-push). Run manually: git push origin {DEV_BRANCH}")
    elif has_remote():
        try:
            git(["push", "origin", DEV_BRANCH], write=True)
            ok(f"Pushed {DEV_BRANCH} to origin.")
        except subprocess.CalledProcessError as exc:
            err(f"Push failed: {(exc.stderr or '').strip()}")
            err(f"Run manually: git push origin {DEV_BRANCH}")
            sys.exit(1)
    else:
        warn("No remote 'origin' configured — skipping push.")

    # Show recent log
    log = git(["log", DEV_BRANCH, "--oneline", f"-{FINAL_LOG_COUNT}"]).strip()
    if not QUIET:
        print(f"\n{C_BOLD}Recent commits on {DEV_BRANCH}:{C_RESET}")
        for line in log.splitlines():
            print(f"  {C_CYAN}{line}{C_RESET}")

    # Final report
    if not QUIET:
        print(f"\n{C_BOLD}{C_GREEN}Merge complete!{C_RESET}")
        print(f"  Branch merged:  {C_BOLD}{feature_branch}{C_RESET}")
        print(f"  Merge commit:   {C_BOLD}{merge_commit}{C_RESET}")
        print(f"  Dev version:    {C_BOLD}{dev_version}{C_RESET}")

    # JSON output
    if args.output_json:
        result = {
            "branch": feature_branch,
            "dev_version": dev_version,
            "merge_commit": merge_commit,
        }
        print(json.dumps(result))

    # Branch switch prompt
    if not NON_INTERACTIVE:
        switch_back = confirm(
            f"Switch back to '{feature_branch}'?", default=False
        )
        if switch_back:
            git(["checkout", feature_branch], write=True)
            ok(f"Switched to '{feature_branch}'.")
        else:
            ok(f"Staying on {DEV_BRANCH}.")
    else:
        ok(f"Staying on {DEV_BRANCH}.")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="merge-to-dev.py",
        description="Merge a feature branch into dev with version restoration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  ./build/merge-to-dev.py                        # full interactive workflow\n"
            "  ./build/merge-to-dev.py --dry-run              # preview without changes\n"
            "  ./build/merge-to-dev.py --non-interactive \\\n"
            "      --no-push                                   # CI/automated, local only\n"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run read operations; print write operations without executing them.",
    )

    stash_group = parser.add_argument_group("stash and recovery")
    stash_group.add_argument(
        "--auto-stash",
        action="store_true",
        help="Auto-stash dirty changes before proceeding; auto-pop at the end.",
    )

    push_group = parser.add_argument_group("push")
    push_group.add_argument(
        "--no-push",
        action="store_true",
        help="Complete all local steps but skip the remote push.",
    )

    ci_group = parser.add_argument_group("CI and output")
    ci_group.add_argument(
        "--non-interactive",
        action="store_true",
        help=(
            "Disable all prompts. Any condition requiring human input without a "
            "corresponding flag aborts with a clear error."
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
            '{"branch", "dev_version", "merge_commit"}.'
        ),
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
    """Entry point: parse args, locate root, run all four steps."""
    global DRY_RUN, NON_INTERACTIVE, NO_COLOR, QUIET, AUTO_STASH, NO_PUSH, PROJECT_ROOT

    args = parse_args()
    DRY_RUN = args.dry_run
    NON_INTERACTIVE = args.non_interactive
    NO_COLOR = args.no_color or not sys.stdout.isatty()
    QUIET = args.quiet
    AUTO_STASH = args.auto_stash
    NO_PUSH = args.no_push
    PROJECT_ROOT = verify_project_root()

    _init_colors()

    if DRY_RUN:
        print(f"{C_YELLOW}{C_BOLD}DRY-RUN mode — no changes will be made.{C_RESET}")
    if NON_INTERACTIVE:
        print(
            f"{C_YELLOW}{C_BOLD}NON-INTERACTIVE mode — all prompts suppressed.{C_RESET}",
            file=sys.stderr,
        )

    if not QUIET:
        print(f"\n{C_BOLD}music-porter: merge-to-dev{C_RESET}")
        print(f"Project root: {PROJECT_ROOT}")

    feature_branch = ""
    try:
        feature_branch = step1_verify_and_sync()
        merge_commit = step2_merge(feature_branch)
        dev_version = step3_restore_version(merge_commit)
        step4_push_and_report(feature_branch, merge_commit, dev_version, args)
    except SystemExit:
        # If we've already switched to dev, try to return to the feature branch
        if feature_branch:
            current = git(["rev-parse", "--abbrev-ref", "HEAD"], check=False).strip()
            if current == DEV_BRANCH and not DRY_RUN:
                try:
                    subprocess.run(
                        ["git", "checkout", feature_branch],
                        capture_output=True,
                        cwd=str(PROJECT_ROOT),
                    )
                    warn(f"Returned to '{feature_branch}' after error.")
                except Exception:
                    warn(f"Could not return to '{feature_branch}' — check git status.")
        raise
    finally:
        _stash_pop()


if __name__ == "__main__":
    main()
