# apple-to-ride-command - Quick Reference Card

## 🚀 Most Common Commands

### Just Starting? Use This:
```bash
./apple-to-ride-command
```
Interactive menu - easiest way to get started!
- **1-N**: Select a playlist by number
- **A**: Process all playlists
- **U**: Enter a URL
- **C**: Copy to USB only
- **X**: Exit

### Full Workflow in One Command:
```bash
./apple-to-ride-command pipeline --playlist "Pop_Workout"
```
Downloads, converts, tags, and prompts for USB copy.

### Process Everything:
```bash
./apple-to-ride-command pipeline --auto --copy-to-usb
```
Processes all configured playlists and copies to USB.

## 📋 Command Cheat Sheet

| What I Want to Do | Command |
|-------------------|---------|
| **Show menu** | `./apple-to-ride-command` |
| **Full workflow** | `./apple-to-ride-command pipeline --playlist "Name"` |
| **Download only** | `./apple-to-ride-command download --playlist "Name"` |
| **Convert only** | `./apple-to-ride-command convert music/Name` |
| **Update tags** | `./apple-to-ride-command tag export/Name --album "Album"` |
| **Restore tags** | `./apple-to-ride-command restore export/Name --all` |
| **Copy to USB** | `./apple-to-ride-command sync-usb export/Name` |
| **Preview changes** | Add `--dry-run` before any command |
| **See details** | Add `--verbose` before any command |
| **Get help** | `./apple-to-ride-command --help` |
| **Command help** | `./apple-to-ride-command [command] --help` |

## 🎯 Common Workflows

### New Playlist from URL
```bash
./apple-to-ride-command pipeline --url "https://music.apple.com/..."
# Asks to save to playlists.conf
# Asks to copy to USB
```

### Update Existing Playlist
```bash
./apple-to-ride-command pipeline --playlist "Pop_Workout"
```

### Batch Update All Playlists
```bash
./apple-to-ride-command pipeline --auto
```

### Re-convert with Force
```bash
./apple-to-ride-command convert music/Pop_Workout --output export/Pop_Workout --force
```

### Quick USB Copy
```bash
./apple-to-ride-command sync-usb
# Copies entire export/ directory
```

## 🔧 Useful Flags

| Flag | What It Does | Example |
|------|-------------|---------|
| `--dry-run` | Preview without changes | `--dry-run convert music/Pop_Workout` |
| `--verbose` | Show detailed info | `--verbose tag export/Pop_Workout --album "Test"` |
| `--force` | Overwrite existing files | `convert music/Pop_Workout --force` |
| `--copy-to-usb` | Auto-copy after pipeline | `pipeline --playlist "Name" --copy-to-usb` |
| `--auto` | No prompts (batch mode) | `pipeline --auto` |

## 📁 Where Files Go

```
music/Pop_Workout/           ← Downloaded M4A files
export/Pop_Workout/          ← Converted MP3 files (flat)
logs/2026-02-17_23-00-00.log ← Execution logs
```

## 🆘 Quick Fixes

### "gamdl not found"
```bash
source .venv/bin/activate
pip install gamdl
```

### "ffmpeg not found"
```bash
brew install ffmpeg
```

### See What Went Wrong
```bash
tail -50 logs/$(ls -t logs/ | head -1)
```

### Test Before Running
```bash
./apple-to-ride-command --dry-run --verbose [command] [options]
```

## 💡 Pro Tips

1. **Always dry-run first** when trying something new
2. **Use verbose mode** when debugging: `--verbose`
3. **Check the logs** if something fails
4. **Interactive menu** is great for occasional use
5. **Pipeline --auto** is perfect for scheduled runs
6. **Original tags are safe** - stored in TXXX frames forever

## 📊 Reading Summary Output

After each operation, you'll see a summary like this:

```
============================================================
  CONVERSION SUMMARY
============================================================
  Status:                  ✅ Completed successfully
```

Look for:
- ✅ = Success
- ⚠️ = Completed with errors (check details)
- ❌ = Failed (check logs)

## 🔗 More Help

- Full guide: `APPLE-TO-RIDE-COMMAND-GUIDE.md`
- Implementation details: `IMPLEMENTATION-SUMMARY.md`
- Built-in help: `./apple-to-ride-command --help`
- Command help: `./apple-to-ride-command [command] --help`

## Version

Current: 1.0.0
