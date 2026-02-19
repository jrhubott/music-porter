# music-porter - Quick Reference Card

## 🚀 Most Common Commands

### Just Starting? Use This:
```bash
./music-porter
```
Interactive menu - easiest way to get started!
- **1-N**: Select a playlist by number
- **A**: Process all playlists
- **U**: Enter a URL
- **C**: Copy to USB only
- **X**: Exit

### Full Workflow in One Command:
```bash
./music-porter pipeline --playlist "Pop_Workout"
```
Downloads, converts, tags, and prompts for USB copy.

### Process Everything:
```bash
./music-porter pipeline --auto --copy-to-usb
```
Processes all configured playlists and copies to USB.

## 📋 Command Cheat Sheet

| What I Want to Do | Command |
|-------------------|---------|
| **Show menu** | `./music-porter` |
| **Full workflow** | `./music-porter pipeline --playlist "Name"` |
| **Download only** | `./music-porter download --playlist "Name"` |
| **Convert only** | `./music-porter convert music/Name` |
| **Convert with quality** | `./music-porter convert music/Name --preset high` |
| **Update tags** | `./music-porter tag export/Name --album "Album"` |
| **Restore tags** | `./music-porter restore export/Name --all` |
| **Copy to USB** | `./music-porter sync-usb export/Name` |
| **Preview changes** | Add `--dry-run` before any command |
| **See details** | Add `--verbose` before any command |
| **Get help** | `./music-porter --help` |
| **Command help** | `./music-porter [command] --help` |

## 🎯 Common Workflows

### New Playlist from URL
```bash
./music-porter pipeline --url "https://music.apple.com/..."
# Asks to save to playlists.conf
# Asks to copy to USB
```

### Update Existing Playlist
```bash
./music-porter pipeline --playlist "Pop_Workout"
```

### Batch Update All Playlists
```bash
./music-porter pipeline --auto
```

### Re-convert with Force
```bash
./music-porter convert music/Pop_Workout --output export/Pop_Workout --force
```

### Quick USB Copy
```bash
./music-porter sync-usb
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
| `--preset` | Quality preset | `convert music/Pop_Workout --preset high` |
| `--quality 0-9` | Custom VBR quality | `convert music/Pop_Workout --preset custom --quality 0` |

## 🎵 Quality Presets

| Preset | Bitrate | File Size | Use Case |
|--------|---------|-----------|----------|
| `lossless` | 320kbps CBR | Largest | **Default** - Maximum quality |
| `high` | ~190-250kbps VBR | Large | High quality, smaller than lossless |
| `medium` | ~165-210kbps VBR | Medium | Balanced quality/size |
| `low` | ~115-150kbps VBR | Small | Space-constrained |
| `custom` | Variable VBR | Custom | Advanced (0=best, 9=worst) |

### Examples:
```bash
# Default (lossless)
./music-porter convert music/Pop_Workout

# High quality VBR
./music-porter convert music/Pop_Workout --preset high

# Custom quality (best)
./music-porter convert music/Pop_Workout --preset custom --quality 0

# Full pipeline with quality
./music-porter pipeline --playlist "Pop_Workout" --preset medium
```

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
./music-porter --dry-run --verbose [command] [options]
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

- Full guide: `MUSIC-PORTER-GUIDE.md`
- Implementation details: `IMPLEMENTATION-SUMMARY.md`
- Built-in help: `./music-porter --help`
- Command help: `./music-porter [command] --help`

## Version

Current: 1.0.0
