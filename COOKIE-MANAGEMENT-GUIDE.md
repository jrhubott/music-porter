# Cookie Management Guide

## Overview

The cookie management system automatically validates Apple Music authentication cookies and can refresh them using your browser. This prevents download failures due to expired cookies.

## Features

✅ **Automatic Cookie Validation**
- Checks cookies at startup
- Shows expiration status (days remaining or days ago)
- Only blocks downloads if cookies are invalid

✅ **Automatic Cookie Refresh**
- Uses Selenium to extract cookies from your browser
- Supports Chrome, Firefox, Safari, and Edge
- Automatically detects and uses your OS default browser
- Interactive login if you're not already logged in
- Creates backup before overwriting (cookies.txt.backup)

✅ **Multi-Browser Support**
- Tries default browser first
- Falls back to other installed browsers
- Clear error messages if all browsers fail

## Installation

### 1. Install Optional Dependencies

```bash
# Activate virtual environment
source .venv/bin/activate

# Install selenium and webdriver-manager
pip install -r requirements-optional.txt
```

This installs:
- `selenium` - Browser automation framework
- `webdriver-manager` - Automatic driver downloads (no manual setup!)

### 2. Verify Installation

```bash
python3 -c "import selenium; print('✓ Selenium installed')"
python3 -c "from webdriver_manager.chrome import ChromeDriverManager; print('✓ webdriver-manager installed')"
```

## Usage

### Cookie Status on Startup

Every command shows cookie status at startup:

```bash
$ ./apple-to-ride-command --dry-run download --playlist 1

apple-to-ride-command v1.0.0
Platform: macOS (Darwin)
Command: download
Cookie status: Cookies valid until 2026-08-16 (178 days remaining)  ✅
```

If cookies are expired:

```bash
Cookie status: Cookies expired on 2026-02-15 (3 days ago)  ⚠️
Downloads will fail until cookies are refreshed
```

### Automatic Cookie Refresh

Use the `--auto-refresh-cookies` flag to automatically refresh expired cookies:

```bash
# Download with auto-refresh
./apple-to-ride-command download --playlist 1 --auto-refresh-cookies

# Pipeline with auto-refresh
./apple-to-ride-command pipeline --playlist 1 --auto-refresh-cookies
```

### Workflow Example: Already Logged In

If you're already logged in to Apple Music in your browser:

```bash
$ ./apple-to-ride-command download --playlist 1 --auto-refresh-cookies

apple-to-ride-command v1.0.0
Platform: macOS (Darwin)
Command: download
Cookie status: Cookies expired on 2026-02-15 (3 days ago)
Downloads will fail until cookies are refreshed

Downloading playlist: Rocking_It
[ERROR] Cookies expired on 2026-02-15 (3 days ago)

Attempting automatic cookie refresh...
Detected default browser: Chrome
Available browsers: Chrome, Safari, Edge
Attempting to use Chrome...
Navigating to music.apple.com...
Extracted 42 cookies from Chrome
Successfully extracted 12 Apple Music cookies
Backup created: cookies.txt.backup
Cookies saved to cookies.txt
Cookie status: Cookies valid until 2026-08-20 (183 days remaining)
Cookie refresh successful, continuing with download

Starting download from Apple Music...
[... download proceeds ...]
```

### Workflow Example: Need to Log In

If you're not logged in, a browser window opens:

```bash
$ ./apple-to-ride-command download --playlist 1 --auto-refresh-cookies

[... startup info ...]

Attempting automatic cookie refresh...
Detected default browser: Chrome
Available browsers: Chrome, Safari, Edge
Attempting to use Chrome...
Navigating to music.apple.com...
Not logged in to Apple Music
Launching visible Chrome for login...

============================================================
Please log in to Apple Music
============================================================
1. A Chrome window has opened
2. Log in to your Apple Music account
3. Once logged in, press Enter here to continue
============================================================

Press Enter after logging in... [you press Enter]

Extracted 42 cookies from Chrome
Successfully extracted 12 Apple Music cookies
Backup created: cookies.txt.backup
Cookies saved to cookies.txt
Cookie status: Cookies valid until 2026-08-20 (183 days remaining)
Cookie refresh successful, continuing with download
```

## Browser Support

The tool automatically detects and uses browsers in this priority:

1. **OS Default Browser** (detected automatically)
2. **Other Installed Browsers** (fallback)

### Supported Browsers

| Browser | macOS | Linux | Windows | Notes |
|---------|-------|-------|---------|-------|
| Chrome | ✅ | ✅ | ✅ | Recommended, best support |
| Firefox | ✅ | ✅ | ✅ | Fully supported |
| Safari | ✅ | ❌ | ❌ | macOS only, no headless mode |
| Edge | ✅ | ✅ | ✅ | Chromium-based, fully supported |

### Browser Detection

The tool detects:
- **Your default browser** (e.g., Chrome set as default in System Settings)
- **All installed browsers** (e.g., Chrome, Safari, Edge in /Applications)

Output example:
```
Detected default browser: Chrome
Available browsers: Chrome, Safari, Edge
Attempting to use Chrome...
```

If the default browser fails, it automatically tries the next available browser.

## Flags

### Cookie Management Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--cookies PATH` | Path to cookies.txt file | `cookies.txt` |
| `--auto-refresh-cookies` | Automatically refresh expired cookies | Disabled |
| `--skip-cookie-validation` | Skip cookie validation (not recommended) | Enabled |

### Usage Examples

```bash
# Use custom cookie file
./apple-to-ride-command download --cookies /path/to/cookies.txt --playlist 1

# Auto-refresh with custom cookie file
./apple-to-ride-command download --cookies /path/to/cookies.txt --auto-refresh-cookies --playlist 1

# Skip validation (not recommended)
./apple-to-ride-command download --skip-cookie-validation --playlist 1
```

## Manual Refresh (Alternative)

If automatic refresh fails or you prefer manual control:

1. Open Chrome/Firefox and go to: https://music.apple.com
2. Log in to your Apple Music account
3. Install browser extension:
   - **Chrome**: "Get cookies.txt LOCALLY" extension
   - **Firefox**: "cookies.txt" extension
4. Click extension icon → Export cookies.txt
5. Save as: `cookies.txt` in project directory
6. Re-run the command

## Troubleshooting

### Selenium Not Installed

```
[ERROR] Selenium not installed. Install with: pip install selenium webdriver-manager
```

**Solution**: Install optional dependencies
```bash
source .venv/bin/activate
pip install -r requirements-optional.txt
```

### No Browsers Found

```
[ERROR] No supported browsers found (Chrome, Firefox, Safari, or Edge)
```

**Solution**: Install a supported browser:
- **macOS**: Install Chrome, Firefox, Safari (built-in), or Edge
- **Linux**: Install chrome/chromium, firefox, or edge
- **Windows**: Install Chrome, Firefox, or Edge

### All Browsers Failed

```
[ERROR] All browsers failed. Please ensure browser is up to date.
```

**Solutions**:
1. Update your browser to the latest version
2. Try a different browser
3. Use manual refresh instead
4. Check browser console for errors

### Browser Opens But Doesn't Extract Cookies

**Solution**: Make sure you:
1. Actually log in to Apple Music (not just music.apple.com)
2. Wait for the page to fully load
3. Press Enter after seeing your Apple Music library

### Cookies Still Invalid After Refresh

```
[ERROR] Cookies still invalid after refresh
```

**Solution**:
1. Make sure you have an active Apple Music subscription
2. Try logging out and back in to music.apple.com
3. Check if your Apple ID is working in a regular browser
4. Use manual refresh to verify cookies work

## Security & Privacy

### What Gets Accessed?

- ✅ **Only music.apple.com cookies** are extracted
- ✅ **No passwords** are accessed or stored
- ✅ **No keychain access** required (unlike browser-cookie3)
- ✅ **Backup created** before overwriting (cookies.txt.backup)

### Where Are Cookies Stored?

- **Local only**: `cookies.txt` in your project directory
- **Never transmitted**: Cookies stay on your machine
- **Standard format**: Netscape HTTP Cookie File format

### Backup Files

Before overwriting cookies.txt, a backup is created:
- **Filename**: `cookies.txt.backup`
- **Location**: Same directory as cookies.txt
- **Purpose**: Restore if refresh fails

To restore:
```bash
cp cookies.txt.backup cookies.txt
```

## Technical Details

### Cookie Validation

The tool validates:
1. **File exists**: `cookies.txt` is present
2. **Required cookie**: `media-user-token` for `.music.apple.com`
3. **Expiration**: Unix timestamp is in the future

### Cookie Format

Standard Netscape HTTP Cookie File format:
```
# Netscape HTTP Cookie File
.music.apple.com	TRUE	/	TRUE	1786904321	media-user-token	<token-value>
```

Fields: `domain | flag | path | secure | expiration | name | value`

### Browser Automation Flow

1. **Detect browsers**: Find default and installed browsers
2. **Launch headless**: Try to extract cookies without UI
3. **Check login**: Detect if user is logged in
4. **Launch visible** (if needed): Open browser for user to log in
5. **Extract cookies**: Get all music.apple.com cookies
6. **Convert format**: Selenium → http.cookiejar → Netscape
7. **Save & validate**: Write to file and verify

## Best Practices

✅ **Use auto-refresh for convenience**
```bash
./apple-to-ride-command pipeline --auto --auto-refresh-cookies
```

✅ **Check status before batch operations**
```bash
./apple-to-ride-command pipeline --dry-run --auto
```

✅ **Keep browser updated**
- Updated browsers work better with Selenium
- WebDriver updates automatically with webdriver-manager

✅ **Stay logged in**
- Keep Apple Music logged in your browser
- Enables fully automatic refresh (no interaction)

❌ **Don't skip validation in production**
```bash
# Bad: Downloads will fail silently with expired cookies
./apple-to-ride-command download --skip-cookie-validation --playlist 1
```

## FAQ

**Q: Do I need to install webdriver manually?**
A: No! `webdriver-manager` automatically downloads the correct driver for your browser.

**Q: Which browser should I use?**
A: The tool automatically uses your OS default browser. Chrome and Edge work best.

**Q: Can I use this on a server without a display?**
A: Yes, but you'll need valid cookies first. Run auto-refresh once on your local machine, then copy cookies.txt to the server.

**Q: How often do cookies expire?**
A: Typically 6 months. The tool shows days remaining on startup.

**Q: Does this work on Linux and Windows?**
A: Yes! The tool auto-detects your OS and uses appropriate methods.

**Q: What if I don't have any browsers installed?**
A: Install Chrome (recommended) or Firefox. Safari is built-in on macOS.

**Q: Is my password stored anywhere?**
A: No. The tool only extracts cookies, never passwords. You log in directly through the browser.

## Summary

The cookie management system makes maintaining Apple Music authentication seamless:

1. **Validation at startup** - Always know your cookie status
2. **Automatic refresh** - One flag to refresh expired cookies
3. **Multi-browser support** - Works with your preferred browser
4. **Interactive fallback** - Opens browser if login needed
5. **Safe backups** - Never lose working cookies

For most users:
```bash
# Install once
pip install -r requirements-optional.txt

# Use always
./apple-to-ride-command pipeline --auto --auto-refresh-cookies
```

That's it! No more manual cookie exports. 🎉
