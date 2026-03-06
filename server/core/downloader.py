"""
core.downloader - Downloader, DownloadStatistics, CookieManager, CookieStatus.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.config import NonInteractivePromptHandler, NullDisplayHandler
from core.constants import (
    APPLE_COOKIE_DOMAIN,
    DEFAULT_COOKIES,
    DEFAULT_DATA_DIR,
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
)
from core.logging import Logger
from core.models import DownloadResult, _DisplayProgress
from core.utils import _is_cancelled

# Third-party: set by _init_third_party()
_MozillaCookieJar = None
_webdriver = None
_ChromeService = None
_ChromeDriverManager = None
_FirefoxService = None
_GeckoDriverManager = None
_Options = None
_FirefoxOptions = None

# ══════════════════════════════════════════════════════════════════
# Section 7: Download Module
# ══════════════════════════════════════════════════════════════════

LOGIN_POLL_INTERVAL = 3   # seconds between login checks
LOGIN_TIMEOUT = 300       # 5 minutes max wait for cookie extraction


class DownloadStatistics:
    """Tracks download operation statistics."""

    def __init__(self):
        self.playlist_total = 0      # Total tracks in playlist
        self.downloaded = 0          # Newly downloaded tracks
        self.skipped = 0             # Already existed
        self.failed = 0              # Failed downloads


class Downloader:
    """Manages downloads from Apple Music using gamdl."""

    def __init__(self, logger=None, venv_python=None, cookie_path=DEFAULT_COOKIES,
                 prompt_handler=None, display_handler=None, cancel_event=None):
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.display_handler = display_handler or NullDisplayHandler()
        self.cancel_event = cancel_event
        self.venv_python = venv_python or sys.executable
        self.cookie_manager = CookieManager(cookie_path, logger=self.logger,
                                            prompt_handler=self.prompt_handler)

    def extract_url_info(self, url):
        """
        Extract key and album name from Apple Music URL.
        Converts 'pop-workout' → ('Pop_Workout', 'Pop Workout')
        """

        # Extract the playlist name from URL
        match = re.search(r'/playlist/([^/]+)/', url)
        if not match:
            return None, None

        raw_name = match.group(1)

        # Convert to key format: pop-workout → Pop_Workout
        words = raw_name.split('-')
        key = '_'.join(word.capitalize() for word in words)

        # Convert to album name format: pop-workout → Pop Workout
        album_name = ' '.join(word.capitalize() for word in words)

        return key, album_name

    def _clean_line(self, line):
        """Remove carriage returns and clean up gamdl output."""
        return line.replace('\r', '').strip()

    def _count_m4a_files(self, directory):
        """Count M4A files in directory (non-hidden files only)."""
        if not os.path.exists(directory):
            return 0

        path = Path(directory)
        m4a_files = [
            f for f in path.rglob("*.m4a")
            if not f.name.startswith('._')
        ]
        return len(m4a_files)

    def download(self, url, output_dir, key=None, confirm=True, dry_run=False,
                 validate_cookies=True, auto_refresh=False):
        """
        Download playlist from Apple Music using gamdl.
        Returns DownloadResult.
        """

        # Extract info from URL if key not provided
        if not key:
            key, album_name = self.extract_url_info(url)
            if not key:
                self.logger.error(f"Could not extract playlist info from URL: {url}")
                return DownloadResult(success=False, key=None, album_name=None, duration=0)
        else:
            _, album_name = self.extract_url_info(url)

        output_path = Path(output_dir)
        start_time = time.time()

        self.logger.info(f"Downloading playlist: {key}")
        self.logger.info(f"  Album name: {album_name}")
        self.logger.info(f"  Output: {output_path}")

        # Validate cookies before download
        if validate_cookies and not dry_run:
            status = self.cookie_manager.validate()

            if status.valid:
                self.logger.ok(status.reason)
            else:
                self.logger.error(status.reason)

                # Try auto-refresh if requested
                if auto_refresh:
                    if self.cookie_manager.auto_refresh():
                        # Refresh succeeded, re-validate
                        status = self.cookie_manager.validate()
                        if status.valid:
                            self.logger.ok("Cookie refresh successful, continuing with download")
                        else:
                            self.logger.error("Cookies still invalid after refresh")
                            self.cookie_manager.show_manual_instructions()
                            return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                    else:
                        self.logger.error("Automatic cookie refresh failed")
                        self.cookie_manager.show_manual_instructions()
                        return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                else:
                    self.cookie_manager.show_manual_instructions()

                    # In interactive mode, offer auto-refresh first
                    if confirm:
                        if self.prompt_handler.confirm("Attempt automatic cookie refresh?", default=True):
                            # User wants to try auto-refresh
                            if self.cookie_manager.auto_refresh():
                                # Refresh succeeded, re-validate
                                status = self.cookie_manager.validate()
                                if status.valid:
                                    self.logger.ok("Cookie refresh successful, continuing with download")
                                else:
                                    self.logger.error("Cookies still invalid after refresh")
                                    return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                            else:
                                self.logger.error("Automatic cookie refresh failed")
                                # Ask if they want to continue anyway
                                if not self.prompt_handler.confirm("Continue without valid cookies?", default=False):
                                    self.logger.info("Aborted")
                                    return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                        else:
                            # User declined auto-refresh, ask if they want to continue
                            if not self.prompt_handler.confirm("Continue without valid cookies?", default=False):
                                self.logger.info("Aborted")
                                return DownloadResult(success=False, key=key, album_name=album_name, duration=0)
                    else:
                        # In auto/non-interactive mode, fail immediately
                        self.logger.error("Cannot continue without valid cookies")
                        return DownloadResult(success=False, key=key, album_name=album_name, duration=0)

        # Confirmation prompt (unless auto mode)
        if confirm:
            if not self.prompt_handler.confirm(f"Download {key}?", default=False):
                self.logger.info(f"Skipping download for {key}")
                return DownloadResult(success=False, key=key, album_name=album_name, duration=0)

        if dry_run:
            self.logger.dry_run(f"Would download: {url}")
            self.logger.dry_run(f"  → Output: {output_path}")
            return DownloadResult(success=True, key=key, album_name=album_name, duration=0)

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        # Run gamdl
        self.logger.info("Starting download from Apple Music...")
        if url:
            url_display = url[:80] + "..." if len(url) > 80 else url
            self.logger.info(f"URL: {url_display}")

        gamdl_data = Path(DEFAULT_DATA_DIR) / "gamdl"
        gamdl_data.mkdir(parents=True, exist_ok=True)
        temp_path = gamdl_data / "temp"
        temp_path.mkdir(exist_ok=True)
        config_path = gamdl_data / "config.json"

        cmd = [
            self.venv_python, "-m", "gamdl",
            "--log-level", "INFO",  # Show download progress, suppress DEBUG
            "--cookies-path", str(self.cookie_manager.cookie_path),
            "--config-path", str(config_path),
            "--temp-path", str(temp_path),
            "-o", str(output_path) + "/",
            url
        ]

        stats = DownloadStatistics()

        # Count files BEFORE download
        files_before = self._count_m4a_files(output_path)

        try:
            self.logger.info(f"Running: {' '.join(cmd)}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # Parse output line by line
            progress = _DisplayProgress(
                self.display_handler, total=0, desc="Downloading",
            )
            verbose = self.logger.verbose
            unrecognized_lines = []
            # Collect every track name gamdl processes (all current playlist
            # tracks — gamdl emits "Downloading" for each, even skips)
            playlist_track_names = []

            try:
                if process.stdout is None:
                    raise RuntimeError("subprocess stdout is None despite PIPE")
                for line in process.stdout:
                    if _is_cancelled(self.cancel_event):
                        process.terminate()
                        self.logger.warn("Download cancelled by user")
                        break
                    # Clean carriage returns to prevent screen scrolling
                    cleaned = self._clean_line(line)

                    # Skip empty lines
                    if not cleaned:
                        continue

                    # Filter out download progress bars (still noisy)
                    if cleaned.startswith('[download]'):
                        continue

                    try:
                        # Extract total track count
                        if '[Track' in cleaned and '/' in cleaned:
                            match = re.search(r'\[Track (\d+)/(\d+)\]', cleaned)
                            if match:
                                total_tracks = int(match.group(2))
                                if stats.playlist_total == 0:
                                    stats.playlist_total = total_tracks
                                    progress.set_total(total_tracks)

                        # Track downloads and show real-time feedback
                        # Note: gamdl emits "Downloading" for EVERY track (even skips),
                        # so we advance the bar here (exactly once per track).
                        if '[INFO' in cleaned and 'Downloading "' in cleaned:
                            # Extract track name
                            match = re.search(r'Downloading "([^"]+)"', cleaned)
                            if match:
                                track_name = match.group(1)
                                # Collect for removed-track detection; gamdl
                                # emits this for all current playlist tracks
                                playlist_track_names.append(track_name)
                                msg = f"Downloading: {track_name}"
                                if verbose:
                                    self.logger.info(msg)
                                else:
                                    self.logger.file_info(msg)
                                progress.update(1)

                        # Track skips and show feedback
                        # Don't update progress here — already counted on the
                        # "Downloading" line that gamdl emits before the skip.
                        elif '[WARNING' in cleaned and 'Skipping "' in cleaned and 'Media file already exists' in cleaned:
                            # Extract track name
                            match = re.search(r'Skipping "([^"]+)"', cleaned)
                            if match:
                                track_name = match.group(1)
                                msg = f"Skipping (already exists): {track_name}"
                                if verbose:
                                    self.logger.info(msg)
                                else:
                                    self.logger.file_info(msg)

                        # Track errors
                        elif 'Finished with' in cleaned and 'error' in cleaned:
                            error_match = re.search(r'Finished with (\d+) error', cleaned)
                            if error_match:
                                stats.failed = int(error_match.group(1))

                        # Collect unrecognized output
                        else:
                            unrecognized_lines.append(cleaned)
                            if '[ERROR' in cleaned or '[CRITICAL' in cleaned:
                                self.logger.error(f"gamdl: {cleaned}")
                            else:
                                self.logger.file_info(f"gamdl: {cleaned}")

                    except Exception as parse_error:
                        # If parsing fails for a line, log and continue without crashing
                        self.logger.file_info(f"Output parse error: {parse_error}")
            finally:
                progress.close()

            process.wait()

            # Count files AFTER download
            files_after = self._count_m4a_files(output_path)

            # Calculate accurate statistics from filesystem
            stats.downloaded = files_after - files_before  # New files
            stats.skipped = files_before  # Existing files

            duration = time.time() - start_time
            if process.returncode == 0:
                self.logger.ok(f"Download complete: {key}")
                return DownloadResult(
                    success=True, key=key, album_name=album_name,
                    duration=duration, playlist_total=stats.playlist_total,
                    downloaded=stats.downloaded, skipped=stats.skipped,
                    failed=stats.failed,
                    playlist_track_names=playlist_track_names)
            else:
                self.logger.error(f"Download failed with exit code {process.returncode}")
                if unrecognized_lines:
                    tail = unrecognized_lines[-10:]
                    self.logger.error("gamdl output:")
                    for err_line in tail:
                        self.logger.error(f"  {err_line}")
                return DownloadResult(
                    success=False, key=key, album_name=album_name,
                    duration=duration, playlist_total=stats.playlist_total,
                    downloaded=stats.downloaded, skipped=stats.skipped,
                    failed=stats.failed,
                    playlist_track_names=playlist_track_names)

        except Exception as e:
            self.logger.error(f"Failed to download {key}: {e}")
            duration = time.time() - start_time
            return DownloadResult(
                success=False, key=key, album_name=album_name,
                duration=duration, playlist_total=stats.playlist_total,
                downloaded=stats.downloaded, skipped=stats.skipped,
                failed=stats.failed)


# ══════════════════════════════════════════════════════════════════
# Section 7.5: Cookie Management Module
# ══════════════════════════════════════════════════════════════════

class CookieStatus:
    """Cookie validation result."""
    def __init__(self):
        self.valid = False
        self.exists = False
        self.has_required_cookie = False
        self.expiration_timestamp: int | None = None
        self.expiration_date: datetime | None = None
        self.days_until_expiration: float | None = None
        self.reason = ""  # Human-readable message


class CookieManager:
    """Manages Apple Music cookie validation and refresh."""

    def __init__(self, cookie_path=DEFAULT_COOKIES, logger=None, prompt_handler=None,
                 audit_logger=None, audit_source='cli'):
        self.cookie_path = Path(cookie_path)
        self.logger = logger or Logger()
        self.prompt_handler = prompt_handler or NonInteractivePromptHandler()
        self.audit_logger = audit_logger
        self._audit_source = audit_source
        self.required_domain = '.music.apple.com'
        self.required_cookie_name = 'media-user-token'

    def validate(self):
        """Validate cookies.txt and check expiration.

        Returns:
            CookieStatus: Validation result with detailed information
        """
        import http.cookiejar
        from datetime import datetime

        status = CookieStatus()

        # Check if file exists
        if not self.cookie_path.exists():
            status.reason = f"Cookie file not found: {self.cookie_path}"
            return status

        status.exists = True

        try:
            # Load cookies using MozillaCookieJar (Netscape format)
            cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_path))
            cookie_jar.load(ignore_discard=True, ignore_expires=True)

            # Find the required cookie
            target_cookie = None
            for cookie in cookie_jar:
                if (cookie.domain == self.required_domain and
                    cookie.name == self.required_cookie_name):
                    target_cookie = cookie
                    break

            if not target_cookie:
                status.reason = f"Required cookie '{self.required_cookie_name}' not found for domain '{self.required_domain}'"
                return status

            status.has_required_cookie = True

            # Check expiration
            if target_cookie.expires is None:
                # Session cookie - no expiration
                status.valid = True
                status.reason = "Cookie is valid (session cookie, no expiration)"
                return status

            status.expiration_timestamp = target_cookie.expires
            status.expiration_date = datetime.fromtimestamp(target_cookie.expires, tz=UTC)

            # Compare with current time
            now = datetime.now(UTC)
            time_diff = status.expiration_date - now
            status.days_until_expiration = time_diff.total_seconds() / 86400

            if time_diff.total_seconds() > 0:
                # Cookie is valid
                status.valid = True
                days = int(status.days_until_expiration)
                date_str = status.expiration_date.strftime('%Y-%m-%d')
                status.reason = f"Cookies valid until {date_str} ({days} days remaining)"
            else:
                # Cookie expired
                days_ago = int(-status.days_until_expiration)
                date_str = status.expiration_date.strftime('%Y-%m-%d')
                status.reason = f"Cookies expired on {date_str} ({days_ago} days ago)"

            return status

        except Exception as e:
            status.reason = f"Failed to validate cookies: {e}"
            return status

    def show_manual_instructions(self):
        """Display step-by-step manual cookie refresh guide."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("Apple Music Cookie Refresh Required")
        self.logger.info("=" * 60)
        self.logger.info("\nYour Apple Music authentication has expired. Follow these steps:\n")
        self.logger.info("1. Open Chrome/Firefox and go to: https://music.apple.com")
        self.logger.info("2. Log in to your Apple Music account")
        self.logger.info("3. Install browser extension:")
        self.logger.info("   - Chrome: 'Get cookies.txt LOCALLY' extension")
        self.logger.info("   - Firefox: 'cookies.txt' extension")
        self.logger.info("4. Click extension icon → Export cookies.txt")
        self.logger.info(f"5. Save as: {self.cookie_path.absolute()}")
        self.logger.info("6. Re-run this command\n")
        self.logger.info("Alternative: Try automatic refresh with --auto-refresh-cookies flag")
        self.logger.info("(opens browser automatically, no password prompts required)")
        self.logger.info("=" * 60 + "\n")

    def _detect_default_browser(self):
        """
        Detect the OS default browser.
        Returns browser name: 'chrome', 'firefox', 'safari', 'edge', or None
        """

        try:
            if IS_MACOS:
                # macOS: Use LaunchServices to get default browser
                result = subprocess.run(
                    ['defaults', 'read', 'com.apple.LaunchServices/com.apple.launchservices.secure', 'LSHandlers'],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout.lower()

                # Check for browser identifiers in output
                if 'chrome' in output or 'google' in output:
                    return 'chrome'
                elif 'firefox' in output:
                    return 'firefox'
                elif 'safari' in output or 'webkit' in output:
                    return 'safari'
                elif 'edge' in output or 'msedge' in output:
                    return 'edge'

            elif IS_LINUX:
                # Linux: Check xdg-settings
                result = subprocess.run(
                    ['xdg-settings', 'get', 'default-web-browser'],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout.lower()

                if 'chrome' in output or 'chromium' in output:
                    return 'chrome'
                elif 'firefox' in output:
                    return 'firefox'
                elif 'edge' in output:
                    return 'edge'

            elif IS_WINDOWS:
                # Windows: Check registry
                import winreg  # type: ignore[import]
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,  # type: ignore[attr-defined]
                                        r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice')
                    prog_id = winreg.QueryValueEx(key, 'ProgId')[0].lower()  # type: ignore[attr-defined]
                    winreg.CloseKey(key)  # type: ignore[attr-defined]

                    if 'chrome' in prog_id:
                        return 'chrome'
                    elif 'firefox' in prog_id:
                        return 'firefox'
                    elif 'edge' in prog_id or 'msedge' in prog_id:
                        return 'edge'
                except Exception:
                    pass

        except Exception as e:
            self.logger.info(f"Could not detect default browser: {e}")

        return None

    def _detect_installed_browsers(self):
        """
        Detect which browsers are installed on the system.
        Returns list of browser names: ['chrome', 'firefox', 'safari', 'edge']
        """

        browsers = []

        if IS_MACOS:
            # Check for browser apps in /Applications
            browser_paths = {
                'chrome': '/Applications/Google Chrome.app',
                'firefox': '/Applications/Firefox.app',
                'safari': '/Applications/Safari.app',
                'edge': '/Applications/Microsoft Edge.app'
            }

            for name, path in browser_paths.items():
                if Path(path).exists():
                    browsers.append(name)

        elif IS_LINUX:
            # Check for browser binaries
            browser_cmds = ['google-chrome', 'chromium', 'firefox', 'microsoft-edge']

            for cmd in browser_cmds:
                if shutil.which(cmd):
                    if 'chrome' in cmd or 'chromium' in cmd:
                        if 'chrome' not in browsers:
                            browsers.append('chrome')
                    elif 'firefox' in cmd:
                        browsers.append('firefox')
                    elif 'edge' in cmd:
                        browsers.append('edge')

        elif IS_WINDOWS:
            # Check for browser executables
            browser_paths = {
                'chrome': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                'firefox': r'C:\Program Files\Mozilla Firefox\firefox.exe',
                'edge': r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
            }

            for name, path in browser_paths.items():
                if Path(path).exists():
                    browsers.append(name)

        return browsers

    def _prompt_browser_selection(self, available_browsers, default_browser):
        """
        Prompt user to select which browser to use.
        Returns list of browsers to try (in order), or None if cancelled.
        """
        if len(available_browsers) == 1:
            # Only one browser available, use it automatically
            return available_browsers

        # Build options: each browser + "Try all browsers"
        options = [
            f"{b.capitalize()}{' (default)' if b == default_browser else ''}"
            for b in available_browsers
        ]
        options.append("Try all browsers")

        selection = self.prompt_handler.select_from_list(
            "Select browser for cookie extraction", options, allow_cancel=True)

        if selection is None:
            return None

        # Last option = "Try all browsers"
        if selection == len(available_browsers):
            self.logger.info("Will try all browsers if needed")
            return available_browsers

        selected = available_browsers[selection]
        self.logger.info(f"Using: {selected.capitalize()}")
        return [selected]

    def _extract_with_selenium(self, browser=None):
        """
        Extract cookies using Selenium WebDriver.
        Tries default browser first, then falls back to others.
        browser: None = interactive prompt, 'auto' = try all detected,
                 'chrome'/'firefox'/'safari'/'edge' = specific browser.
        Returns cookie_jar on success, None on failure.
        """


        # Detect browsers
        default_browser = self._detect_default_browser()
        installed_browsers = self._detect_installed_browsers()

        # Build priority list: default first, then others
        browser_priority = []
        if default_browser and default_browser in installed_browsers:
            browser_priority.append(default_browser)
            self.logger.info(f"Detected default browser: {default_browser.capitalize()}")

        for b in installed_browsers:
            if b not in browser_priority:
                browser_priority.append(b)

        if not browser_priority:
            self.logger.error("No supported browsers found (Chrome, Firefox, Safari, or Edge)")
            return None

        # Determine which browsers to try
        interactive = browser is None
        if browser is None:
            # CLI interactive mode — prompt user
            selected_browsers = self._prompt_browser_selection(browser_priority, default_browser)
            if not selected_browsers:
                self.logger.info("Browser selection cancelled")
                return None
        elif browser == 'auto':
            # Non-interactive: try all detected browsers
            selected_browsers = browser_priority
            self.logger.info(f"Auto mode: will try {', '.join(b.capitalize() for b in selected_browsers)}")
        else:
            # Non-interactive: specific browser requested
            if browser not in installed_browsers:
                self.logger.error(f"Browser '{browser}' is not installed or not supported")
                return None
            selected_browsers = [browser]
            self.logger.info(f"Using specified browser: {browser.capitalize()}")

        # Try each selected browser
        # Non-interactive mode launches visible so the user can log in if needed
        headless = interactive  # CLI tries headless first; web UI goes visible
        for browser_name in selected_browsers:
            self.logger.info(f"Attempting to use {browser_name.capitalize()}...")

            try:
                driver = self._launch_browser(browser_name, headless=headless)
                if driver:
                    cookies = self._extract_cookies_from_driver(
                        driver, browser_name, interactive=interactive)
                    if cookies:
                        return cookies

            except Exception as e:
                self.logger.info(f"{browser_name.capitalize()} failed: {e}")
                continue

        self.logger.error("All browsers failed. Please ensure browser is up to date.")
        return None

    def _find_cached_driver(self, driver_name):
        """Search webdriver-manager cache for a previously downloaded driver binary.

        Returns the path to the most recent cached binary, or None.
        """
        wdm_dir = Path.home() / '.wdm' / 'drivers' / driver_name
        if not wdm_dir.exists():
            return None

        # Find all driver binaries (exclude .zip files)
        binary_name = driver_name + '.exe' if IS_WINDOWS else driver_name
        matches = sorted(
            [p for p in wdm_dir.rglob(binary_name) if p.is_file() and p.suffix != '.zip'],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            self.logger.info(f"Found cached driver: {matches[0]}")
            return str(matches[0])
        return None

    def _launch_browser(self, browser_name, headless=True):
        """Launch browser with Selenium. Returns driver or None."""

        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.chrome.webdriver import WebDriver as _ChromeDriver
        from selenium.webdriver.edge.service import Service as EdgeService
        from selenium.webdriver.edge.webdriver import WebDriver as _EdgeDriver
        from selenium.webdriver.firefox.service import Service as FirefoxService
        from selenium.webdriver.firefox.webdriver import WebDriver as _FirefoxDriver

        try:
            # Try to import webdriver-manager
            ChromeDriverManager: Any = None
            GeckoDriverManager: Any = None
            EdgeChromiumDriverManager: Any = None
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from webdriver_manager.firefox import GeckoDriverManager
                from webdriver_manager.microsoft import EdgeChromiumDriverManager
                use_manager = True
            except ImportError:
                self.logger.info("webdriver-manager not installed, using system drivers")
                use_manager = False

            driver = None

            def _try_with_fallbacks(manager_fn, cached_fn, direct_fn):
                """Try webdriver-manager → cached driver → system driver."""
                if use_manager:
                    try:
                        return manager_fn()
                    except Exception as mgr_err:
                        self.logger.info(f"webdriver-manager failed ({mgr_err}), trying cached driver")
                # Try cached driver from previous webdriver-manager run
                try:
                    result = cached_fn()
                    if result:
                        return result
                except Exception:
                    pass
                self.logger.info("No cached driver found, trying system driver")
                return direct_fn()

            if browser_name == 'chrome':
                from selenium.webdriver.chrome.options import Options
                options = Options()
                if headless:
                    options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")

                def _cached_chrome():
                    path = self._find_cached_driver('chromedriver')
                    if path:
                        return _ChromeDriver(service=ChromeService(path), options=options)

                driver = _try_with_fallbacks(
                    lambda: _ChromeDriver(service=ChromeService(ChromeDriverManager().install()), options=options),
                    _cached_chrome,
                    lambda: _ChromeDriver(options=options),
                )

            elif browser_name == 'firefox':
                from selenium.webdriver.firefox.options import Options
                options = Options()
                if headless:
                    options.add_argument("--headless")

                def _cached_firefox():
                    path = self._find_cached_driver('geckodriver')
                    if path:
                        return _FirefoxDriver(service=FirefoxService(path), options=options)

                driver = _try_with_fallbacks(
                    lambda: _FirefoxDriver(service=FirefoxService(GeckoDriverManager().install()), options=options),
                    _cached_firefox,
                    lambda: _FirefoxDriver(options=options),
                )

            elif browser_name == 'edge':
                from selenium.webdriver.edge.options import Options
                options = Options()
                if headless:
                    options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")

                def _cached_edge():
                    path = self._find_cached_driver('msedgedriver')
                    if path:
                        return _EdgeDriver(service=EdgeService(path), options=options)

                driver = _try_with_fallbacks(
                    lambda: _EdgeDriver(service=EdgeService(EdgeChromiumDriverManager().install()), options=options),
                    _cached_edge,
                    lambda: _EdgeDriver(options=options),
                )

            elif browser_name == 'safari':
                # Safari doesn't support headless mode and doesn't need webdriver-manager
                if headless:
                    self.logger.info("Safari doesn't support headless mode, launching visible browser")
                driver = webdriver.Safari()  # type: ignore[attr-defined]

            return driver

        except WebDriverException as e:
            self.logger.info(f"Failed to launch {browser_name}: {e}")
            return None
        except Exception as e:
            self.logger.info(f"Unexpected error launching {browser_name}: {e}")
            return None

    def _extract_cookies_from_driver(self, driver, browser_name, interactive=True):
        """Extract cookies from Selenium driver. Returns cookie_jar or None.

        interactive: True = prompt via prompt_handler after login (CLI mode),
                     False = poll for login automatically (web UI mode).
        """
        import http.cookiejar
        import time

        try:
            # Navigate to Apple Music
            self.logger.info("Navigating to music.apple.com...")
            driver.get("https://music.apple.com")
            time.sleep(3)  # Wait for page load

            # Check if logged in
            is_logged_in = self._check_login_status(driver)

            if not is_logged_in:
                self.logger.warn("Not logged in to Apple Music")

                if interactive:
                    # CLI mode: quit headless, relaunch visible, wait for user
                    driver.quit()
                    self.logger.info(f"Launching visible {browser_name.capitalize()} for login...")
                    driver = self._launch_browser(browser_name, headless=False)
                    if not driver:
                        return None

                    driver.get("https://music.apple.com")

                    self.logger.info("\n" + "=" * 60)
                    self.logger.info("Please log in to Apple Music")
                    self.logger.info("=" * 60)
                    self.logger.info(f"1. A {browser_name.capitalize()} window has opened")
                    self.logger.info("2. Log in to your Apple Music account")
                    self.logger.info("3. Once logged in, press Enter here to continue")
                    self.logger.info("=" * 60 + "\n")

                    self.prompt_handler.wait_for_continue("Press Enter after logging in...")
                    time.sleep(2)  # Let cookies settle
                else:
                    # Web UI mode: browser is already visible, poll for login
                    self.logger.info("=" * 60)
                    self.logger.info("Please log in to Apple Music in the browser window")
                    self.logger.info(f"Waiting up to {LOGIN_TIMEOUT // 60} minutes...")
                    self.logger.info("=" * 60)

                    elapsed = 0
                    while elapsed < LOGIN_TIMEOUT:
                        time.sleep(LOGIN_POLL_INTERVAL)
                        elapsed += LOGIN_POLL_INTERVAL
                        if self._check_login_status(driver):
                            self.logger.ok("Login detected!")
                            time.sleep(2)  # Let cookies settle
                            break
                    else:
                        self.logger.error("Login timed out. Please try again.")
                        driver.quit()
                        return None

            # Extract cookies
            selenium_cookies = driver.get_cookies()
            self.logger.info(f"Extracted {len(selenium_cookies)} cookies from {browser_name.capitalize()}")

            # Convert to http.cookiejar format
            cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_path))
            target_cookie_found = False

            for sc in selenium_cookies:
                # Only process cookies for music.apple.com domain
                domain = sc.get('domain', '')
                if 'music.apple.com' not in domain:
                    continue

                # Create http.cookiejar.Cookie object
                cookie = http.cookiejar.Cookie(
                    version=0,
                    name=sc['name'],
                    value=sc['value'],
                    port=None,
                    port_specified=False,
                    domain=domain,
                    domain_specified=True,
                    domain_initial_dot=domain.startswith('.'),
                    path=sc.get('path', '/'),
                    path_specified=True,
                    secure=sc.get('secure', False),
                    expires=sc.get('expiry'),  # Unix timestamp or None
                    discard=False,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False
                )
                cookie_jar.set_cookie(cookie)

                if sc['name'] == self.required_cookie_name:
                    target_cookie_found = True

            driver.quit()

            if not target_cookie_found:
                self.logger.error(f"Cookie '{self.required_cookie_name}' not found after extraction")
                return None

            music_cookies = [c for c in cookie_jar if 'music.apple.com' in c.domain]
            self.logger.ok(f"Successfully extracted {len(music_cookies)} Apple Music cookies")
            return cookie_jar

        except Exception as e:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            self.logger.error(f"Cookie extraction failed: {e}")
            return None

    def _check_login_status(self, driver):
        """Check if user is logged in to Apple Music. Returns True if logged in."""
        from selenium.webdriver.common.by import By

        try:
            # Strategy: Look for sign-in button. If found, user is NOT logged in.
            # This is more reliable than looking for profile elements which vary
            sign_in_buttons = driver.find_elements(By.XPATH,
                "//a[contains(@href, 'signin') or contains(@href, 'sign-in') or contains(text(), 'Sign In')]")

            if sign_in_buttons:
                return False  # Sign-in button found = not logged in

            # Additional check: Look for account/profile indicators
            account_indicators = driver.find_elements(By.XPATH,
                "//button[contains(@aria-label, 'Account') or contains(@aria-label, 'account')]")

            if account_indicators:
                return True  # Account button found = logged in

            # Default: assume not logged in to be safe
            return False

        except Exception as e:
            self.logger.info(f"Login check uncertain: {e}")
            return False  # Assume not logged in on error

    def auto_refresh(self, backup=True, browser=None):
        """
        Automatically refresh cookies using Selenium.
        Creates backup before overwriting if backup=True.
        browser: None = interactive prompt (CLI), 'auto' = try all browsers,
                 'chrome'/'firefox'/'safari'/'edge' = specific browser.
        Returns True if successful, False otherwise.
        """
        self.logger.info("Attempting automatic cookie refresh...")

        # Extract cookies using Selenium
        cookie_jar = self._extract_with_selenium(browser=browser)

        if not cookie_jar:
            self.logger.error("Automatic cookie refresh failed")
            if self.audit_logger:
                self.audit_logger.log(
                    'cookie_refresh', 'Cookie auto-refresh failed',
                    'failed', source=self._audit_source)
            return False

        # Create backup if requested and file exists
        if backup and self.cookie_path.exists():
            backup_path = Path(str(self.cookie_path) + '.backup')
            shutil.copy2(self.cookie_path, backup_path)
            self.logger.ok(f"Backup created: {backup_path}")

        # Save cookies in Netscape format
        try:
            cookie_jar.save(ignore_discard=True, ignore_expires=False)
            self.logger.ok(f"Cookies saved to {self.cookie_path}")

            # Validate the new cookies
            status = self.validate()
            if status.valid:
                self.logger.ok(status.reason)
                if self.audit_logger:
                    self.audit_logger.log(
                        'cookie_refresh', 'Cookie auto-refresh succeeded',
                        'completed', source=self._audit_source)
                return True
            else:
                self.logger.error(f"Saved cookies are not valid: {status.reason}")
                if self.audit_logger:
                    self.audit_logger.log(
                        'cookie_refresh', 'Cookie refresh: saved cookies invalid',
                        'failed', source=self._audit_source)
                return False

        except Exception as e:
            self.logger.error(f"Failed to save cookies: {e}")
            if self.audit_logger:
                self.audit_logger.log(
                    'cookie_refresh', f'Cookie refresh error: {e}',
                    'failed', source=self._audit_source)
            return False

    def clean_cookies(self):
        """Remove non-Apple cookies from cookies.txt file.

        Filters the cookie file to only retain cookies whose domain
        contains 'apple.com'. Creates a backup before modifying.

        Returns:
            tuple: (success: bool, kept: int, removed: int)
        """
        if not self.cookie_path.exists():
            return (False, 0, 0)

        try:
            import http.cookiejar
            cookie_jar = http.cookiejar.MozillaCookieJar(str(self.cookie_path))
            cookie_jar.load(ignore_discard=True, ignore_expires=True)

            all_cookies = list(cookie_jar)
            apple_cookies = [c for c in all_cookies if APPLE_COOKIE_DOMAIN in c.domain]
            removed_count = len(all_cookies) - len(apple_cookies)

            if removed_count == 0:
                return (True, len(apple_cookies), 0)

            # Create backup before modifying
            backup_path = Path(str(self.cookie_path) + '.backup')
            shutil.copy2(self.cookie_path, backup_path)

            # Clear and re-add only Apple cookies
            cookie_jar.clear()
            for cookie in apple_cookies:
                cookie_jar.set_cookie(cookie)

            cookie_jar.save(ignore_discard=True, ignore_expires=False)
            return (True, len(apple_cookies), removed_count)

        except Exception as e:
            self.logger.error(f"Cookie cleanup failed: {e}")
            return (False, 0, 0)


