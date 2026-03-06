"""
core.logging - Logger, ProgressBar, and MigrationEvent.
"""
from __future__ import annotations

import sys
import threading
from dataclasses import field
from datetime import datetime
from pathlib import Path

from core.constants import DEFAULT_LOG_DIR

# _tqdm is lazily set by _init_third_party(); Logger uses it for output routing.
_tqdm = None

# ══════════════════════════════════════════════════════════════════
# Section 2: Logging Infrastructure
# ══════════════════════════════════════════════════════════════════

class Logger:
    """Manages logging to both console and timestamped log file."""

    def __init__(self, log_dir=DEFAULT_LOG_DIR, verbose=False, echo_to_console=True):
        self.verbose = verbose
        self.echo_to_console = echo_to_console
        self._lock = threading.Lock()
        self._active_bars = []
        self.log_file = None

        try:
            self.log_dir = Path(log_dir)
            self.log_dir.mkdir(exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            self.log_file = self.log_dir / f"{date_str}.log"
            # Verify we can write to the log file (creates or appends)
            self.log_file.touch()
        except PermissionError:
            self.log_file = None
            if echo_to_console:
                print(f"Warning: Permission denied writing to {log_dir}/. "
                      "File logging disabled for this session.")

    def register_bar(self, bar):
        """Register an active tqdm bar for write routing."""
        self._active_bars.append(bar)

    def unregister_bar(self, bar):
        """Unregister a tqdm bar."""
        try:
            self._active_bars.remove(bar)
        except ValueError:
            pass

    def _write(self, level, message):
        """Write message to both console and log file."""
        with self._lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_with_prefix = f"[{timestamp}] [{level}] {message}"

            # Console: route through tqdm.write() if a bar is active
            if self.echo_to_console:
                if self._active_bars and _tqdm is not None:
                    _tqdm.write(message)
                else:
                    print(message)

            # File: full format with timestamp and level
            if self.log_file:
                try:
                    with open(self.log_file, 'a') as f:
                        f.write(formatted_with_prefix + '\n')
                except PermissionError:
                    pass

    def _write_file_only(self, level, message):
        """Write message to log file only (no console output)."""
        if not self.log_file:
            return
        with self._lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_with_prefix = f"[{timestamp}] [{level}] {message}"

            # File only: full format with timestamp and level
            try:
                with open(self.log_file, 'a') as f:
                    f.write(formatted_with_prefix + '\n')
            except PermissionError:
                pass

    def info(self, message):
        """Log informational message."""
        self._write("INFO", message)

    def file_info(self, message):
        """Log informational message to file only."""
        self._write_file_only("INFO", message)

    def warn(self, message):
        """Log warning message."""
        self._write("WARN", message)

    def error(self, message):
        """Log error message."""
        self._write("ERROR", message)

    def skip(self, message):
        """Log skip message."""
        self._write("SKIP", message)

    def ok(self, message):
        """Log success message."""
        self._write("OK", message)

    def dry_run(self, message):
        """Log dry-run message."""
        self._write("DRY-RUN", message)

    def debug(self, message):
        """Log debug message (only if verbose enabled)."""
        if self.verbose:
            self._write("VERBOSE", message)


class ProgressBar:
    """Context manager wrapping tqdm with project conventions.

    Disables gracefully during dry-run or when disable=True.
    Supports deferred initialization via set_total() for
    cases where the total isn't known upfront (e.g. Downloader).

    Saves and restores terminal state around the tqdm bar lifetime to
    prevent input() from hanging after the bar closes.
    """

    def __init__(self, total=0, desc="Processing", logger=None,
                 unit="file", disable=False):
        self._desc = desc
        self._unit = unit
        self._disabled = disable
        self._bar = None
        self.logger = logger
        self.total = total
        self._saved_termios = None
        self._current = 0
        self._update_lock = threading.Lock()
        self._progress_callback = None

        # If the logger supports progress callbacks (e.g. WebLogger), wire it up
        if logger and hasattr(logger, '_make_progress_callback'):
            self._progress_callback = logger._make_progress_callback()

        if not self._disabled and total > 0:
            self._create_bar(total)

    def _save_terminal(self):
        """Save terminal attributes before tqdm takes over."""
        try:
            import termios
            self._saved_termios = termios.tcgetattr(sys.stdin)
        except Exception:
            pass

    def _restore_terminal(self):
        """Restore terminal attributes after tqdm is done."""
        if self._saved_termios is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._saved_termios)
            except Exception:
                pass
            self._saved_termios = None

    def _create_bar(self, total):
        """Create the underlying tqdm bar."""
        self._save_terminal()
        self._bar = _tqdm(
            total=total,
            desc=self._desc,
            unit=self._unit,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            dynamic_ncols=True,
        )
        if self.logger:
            self.logger.register_bar(self._bar)

    def set_total(self, total):
        """Lazily initialize the bar when total becomes known."""
        self.total = total
        if self._bar is not None or self._disabled:
            return
        self._create_bar(total)

    def update(self, n=1):
        """Advance the progress bar."""
        if self._bar is not None:
            self._bar.update(n)
        if self._progress_callback is not None:
            with self._update_lock:
                self._current += n
            self._progress_callback(self._current, self.total, self._desc)

    def close(self):
        """Close the progress bar and unregister from logger."""
        if self._bar is not None:
            try:
                self._bar.close()
            finally:
                if self.logger:
                    self.logger.unregister_bar(self._bar)
                self._bar = None
                self._restore_terminal()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class MigrationEvent:
    """Deferred audit entry for schema/data migrations that run before AuditLogger exists."""
    operation: str
    description: str
    status: str
    params: dict = field(default_factory=dict)


