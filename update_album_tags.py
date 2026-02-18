#!/usr/bin/env python3
"""
update_album_tags.py - Update MP3 tags for all files in a directory.

Usage:
    ./update_album_tags.py /path/to/music "New Album Name"
    ./update_album_tags.py /path/to/music --new-album "New Album Name"
    ./update_album_tags.py /path/to/music --restore-all
    ./update_album_tags.py /path/to/music --restore-album
    ./update_album_tags.py /path/to/music --restore-title
    ./update_album_tags.py /path/to/music --restore-artist
"""

import sys
import subprocess
import os
import argparse


def check_and_install_mutagen():
    """Check if mutagen is installed, and install it if not."""
    try:
        import mutagen
        print(f"[INFO] mutagen {mutagen.version_string} already installed.")
    except ImportError:
        print("[INFO] mutagen not found. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
            print("[INFO] mutagen installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to install mutagen: {e}")
            print("[ERROR] Try running: pip3 install mutagen")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Update the Album MP3 tag for all files in a directory,\n"
            "storing the original album name in a custom tag,\n"
            "storing the original title in a custom tag,\n"
            "storing the original artist in a custom tag,\n"
            "removing all other tags, updating the title to\n"
            "'Artist Name - Title' format, and setting Artist to 'Various'.\n"
            "\n"
            "Can also restore any or all original tags.\n"
            "\n"
            "By default:\n"
            "  - ID3v1 tags are removed\n"
            "  - Tags are written as ID3v2.3\n"
            "  - Duplicate tag frames are removed"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Update tags:\n"
            "  ./update_album_tags.py /path/to/music \"New Album Name\"\n"
            "  ./update_album_tags.py /path/to/music --new-album \"New Album Name\"\n"
            "  ./update_album_tags.py /path/to/music \"New Album Name\" --new-artist \"Compilations\"\n"
            "\n"
            "  # Restore all original tags:\n"
            "  ./update_album_tags.py /path/to/music --restore-all\n"
            "\n"
            "  # Restore individual tags:\n"
            "  ./update_album_tags.py /path/to/music --restore-album\n"
            "  ./update_album_tags.py /path/to/music --restore-title\n"
            "  ./update_album_tags.py /path/to/music --restore-artist\n"
            "\n"
            "  # Restore multiple tags:\n"
            "  ./update_album_tags.py /path/to/music --restore-album --restore-artist\n"
            "\n"
            "  # Override default tag cleanup:\n"
            "  ./update_album_tags.py /path/to/music \"Album\" --keep-id3v1\n"
            "  ./update_album_tags.py /path/to/music \"Album\" --keep-id3v24\n"
            "  ./update_album_tags.py /path/to/music \"Album\" --keep-duplicates\n"
        )
    )

    # Required positional argument - directory is always required
    parser.add_argument(
        "directory",
        help="Path to the directory containing MP3 files"
    )

    # Optional positional argument - album name can be passed as second positional arg
    parser.add_argument(
        "album_positional",
        nargs="?",
        default=None,
        metavar="ALBUM_NAME",
        help="New album name (can also be passed with --new-album)"
    )

    # Update options
    update_group = parser.add_argument_group("Update Options")
    update_group.add_argument(
        "--new-album",
        default=None,
        metavar="ALBUM_NAME",
        help="New album name to set (can also be passed as second positional argument)"
    )
    update_group.add_argument(
        "--new-artist",
        default="Various",
        metavar="ARTIST_NAME",
        help="New artist name to set (default: Various)"
    )
    update_group.add_argument(
        "--original-tag",
        default="OriginalAlbum",
        metavar="TAG_NAME",
        help="Name of the custom tag to store the original album name (default: OriginalAlbum)"
    )
    update_group.add_argument(
        "--original-title-tag",
        default="OriginalTitle",
        metavar="TAG_NAME",
        help="Name of the custom tag to store the original title (default: OriginalTitle)"
    )
    update_group.add_argument(
        "--original-artist-tag",
        default="OriginalArtist",
        metavar="TAG_NAME",
        help="Name of the custom tag to store the original artist (default: OriginalArtist)"
    )

    # Restore options
    restore_group = parser.add_argument_group("Restore Options")
    restore_group.add_argument(
        "--restore-all",
        action="store_true",
        help="Restore all original tags (album, title, and artist)"
    )
    restore_group.add_argument(
        "--restore-album",
        action="store_true",
        help="Restore the original album tag"
    )
    restore_group.add_argument(
        "--restore-title",
        action="store_true",
        help="Restore the original title tag"
    )
    restore_group.add_argument(
        "--restore-artist",
        action="store_true",
        help="Restore the original artist tag"
    )

    # Tag cleanup options
    cleanup_group = parser.add_argument_group(
        "Tag Cleanup Options",
        "By default: ID3v1 tags are removed, ID3v2.3 is used, duplicate frames are removed.\n"
        "Use these flags to override the defaults."
    )
    cleanup_group.add_argument(
        "--keep-id3v1",
        action="store_true",
        help="Keep ID3v1 tags (default: remove them)"
    )
    cleanup_group.add_argument(
        "--keep-id3v24",
        action="store_true",
        help="Write ID3v2.4 tags instead of ID3v2.3 (default: use ID3v2.3)"
    )
    cleanup_group.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="Keep duplicate tag frames (default: remove them)"
    )

    # Parse args first so --help works without triggering mutagen install
    args = parser.parse_args()

    # Reconcile album name from positional or --new-album flag
    # --new-album takes precedence if both are provided
    new_album = args.new_album or args.album_positional

    # Warn if both were provided
    if args.new_album and args.album_positional:
        print(f"[WARN] Album name provided twice. Using --new-album value: '{args.new_album}'")
        print(f"       Ignoring positional value: '{args.album_positional}'\n")

    # Determine if we are in restore mode
    restoring = args.restore_all or args.restore_album or args.restore_title or args.restore_artist

    # Validate: album name is required if not restoring
    if not restoring and new_album is None:
        parser.error(
            "Album name is required when not using a restore option.\n"
            "  Positional:  ./update_album_tags.py /path/to/music \"Album Name\"\n"
            "  Flag:        ./update_album_tags.py /path/to/music --new-album \"Album Name\"\n"
            "  Restore:     ./update_album_tags.py /path/to/music --restore-all"
        )

    # Only check/install mutagen after --help has been handled
    check_and_install_mutagen()

    # Build cleanup options dict to pass to functions
    cleanup_options = {
        "remove_id3v1":      not args.keep_id3v1,
        "use_id3v23":        not args.keep_id3v24,
        "remove_duplicates": not args.keep_duplicates,
    }

    if restoring:
        restore_tags(
            directory=args.directory,
            restore_album=args.restore_all  or args.restore_album,
            restore_title=args.restore_all  or args.restore_title,
            restore_artist=args.restore_all or args.restore_artist,
            original_album_tag_name=args.original_tag,
            original_title_tag_name=args.original_title_tag,
            original_artist_tag_name=args.original_artist_tag,
            cleanup_options=cleanup_options
        )
    else:
        update_album_tags(
            directory=args.directory,
            new_album_name=new_album,
            original_album_tag_name=args.original_tag,
            original_title_tag_name=args.original_title_tag,
            original_artist_tag_name=args.original_artist_tag,
            new_artist_name=args.new_artist,
            cleanup_options=cleanup_options
        )


def save_original_tag(tags, tag_key, tag_name, current_value, label):
    """
    Save the original value in a TXXX tag only if it doesn't already exist.

    Args:
        tags: The ID3 tags object
        tag_key (str): The full TXXX tag key (e.g. "TXXX:OriginalAlbum")
        tag_name (str): The description name for the TXXX tag
        current_value (str): The current value to save
        label (str): Human readable label for logging (e.g. "album", "title", "artist")

    Returns:
        str: The protected original value (either existing or newly saved)
    """
    from mutagen.id3 import TXXX

    if tag_key in tags:
        existing_value = str(tags[tag_key])
        print(f"  [SKIP] Original {label} tag already exists: '{existing_value}'. Not overwriting.")
        return existing_value

    if current_value:
        tags.add(TXXX(encoding=3, desc=tag_name, text=current_value))
        print(f"  [INFO] Stored original {label} '{current_value}' in '{tag_name}' tag.")
        return current_value
    else:
        print(f"  [INFO] No existing {label} tag found. Skipping original {label} save.")
        return None


def build_new_title(original_artist, original_title):
    """
    Build the new title in the format "Artist - Title" using the
    original artist and original title values.

    Args:
        original_artist (str): The original artist name
        original_title (str): The original title

    Returns:
        str: The new title in "Artist - Title" format, or None if both are missing
    """
    if original_artist and original_title:
        return f"{original_artist} - {original_title}"
    elif original_title:
        return original_title
    else:
        return None


def apply_cleanup(tags, filepath, cleanup_options):
    """
    Apply tag cleanup operations to a file.

    - Remove duplicate tag frames
    - Remove ID3v1 tags
    - Write ID3v2.3 or ID3v2.4 tags

    Args:
        tags: The mutagen ID3 tags object
        filepath (str): Path to the MP3 file
        cleanup_options (dict): Dict of cleanup options:
            remove_id3v1 (bool): Whether to remove ID3v1 tags
            use_id3v23 (bool): Whether to write ID3v2.3 tags
            remove_duplicates (bool): Whether to remove duplicate tag frames

    Returns:
        list: List of cleanup actions actually performed
    """
    actions = []

    # --- Remove Duplicate Tag Frames ---
    if cleanup_options.get("remove_duplicates"):
        seen  = {}
        dupes = []

        for key in tags.keys():
            # Get the base frame name e.g. "TIT2" from "TIT2" or "TXXX:something"
            base = key.split(":")[0]
            # Only check standard single-value frames, not TXXX which can have
            # multiple legitimate entries with different descriptions
            if base != "TXXX":
                if base in seen:
                    dupes.append(key)
                else:
                    seen[base] = key

        if dupes:
            for dupe in dupes:
                del tags[dupe]
            actions.append(f"Removed duplicate frames: {', '.join(dupes)}")
            print(f"  [INFO] Removed duplicate frames: {', '.join(dupes)}")
        else:
            print(f"  [INFO] No duplicate frames found.")

    # --- Check existing ID3 version before saving ---
    try:
        existing_version = tags.version[1]  # e.g. 3 for ID3v2.3, 4 for ID3v2.4
    except Exception:
        existing_version = None

    # --- Check if ID3v1 tags actually exist ---
    id3v1_exists = False
    if cleanup_options.get("remove_id3v1"):
        try:
            with open(filepath, 'rb') as f:
                # ID3v1 tags are always 128 bytes at the end of the file
                # and start with the marker "TAG"
                f.seek(-128, 2)
                id3v1_exists = f.read(3) == b'TAG'
        except Exception:
            id3v1_exists = False

    # --- Save with correct ID3 version ---
    # v1=0 tells mutagen to strip ID3v1 tags on save
    # v1=1 tells mutagen to update/keep ID3v1 tags on save
    # v1=2 tells mutagen to write ID3v1 tags even if they don't exist
    target_version = 3 if cleanup_options.get("use_id3v23") else 4
    v1_flag        = 0 if cleanup_options.get("remove_id3v1") else 1

    tags.save(filepath, v2_version=target_version, v1=v1_flag)

    # Only report ID3v2 version change if it actually changed
    if existing_version != target_version:
        actions.append(f"Converted ID3v2.{existing_version or '?'} -> ID3v2.{target_version}")
        print(f"  [INFO] Converted ID3v2.{existing_version or '?'} -> ID3v2.{target_version}")
    else:
        print(f"  [INFO] ID3v2.{target_version} already correct, no conversion needed.")

    # Only report ID3v1 removal if tags actually existed
    if cleanup_options.get("remove_id3v1"):
        if id3v1_exists:
            actions.append("Removed ID3v1 tags")
            print(f"  [INFO] Removed ID3v1 tags")
        else:
            print(f"  [INFO] No ID3v1 tags found.")

    return actions


def print_summary(results):
    """
    Print a summary of all changes made.

    Args:
        results (list): List of dicts containing per-file results
    """
    total           = len(results)
    updated         = [r for r in results if r["status"] == "updated"]
    skipped         = [r for r in results if r["status"] == "skipped"]
    errored         = [r for r in results if r["status"] == "error"]
    album_changes   = [r for r in updated  if r.get("album_changed")]
    title_changes   = [r for r in updated  if r.get("title_changed")]
    artist_changes  = [r for r in updated  if r.get("artist_changed")]
    tag_removals    = [r for r in updated  if r.get("tags_removed")]
    dupe_removals   = [r for r in results  if r.get("duplicates_removed")]
    id3v1_removed   = [r for r in results  if r.get("id3v1_removed")]
    id3v2_converted = [r for r in results  if r.get("id3v2_converted")]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total files processed:      {total}")
    print(f"  Files updated:              {len(updated)}")
    print(f"  Files skipped:              {len(skipped)}")
    print(f"  Files with errors:          {len(errored)}")
    print()
    print(f"  Tag changes across all files:")
    print(f"    Album updated:            {len(album_changes)}")
    print(f"    Title updated:            {len(title_changes)}")
    print(f"    Artist updated:           {len(artist_changes)}")
    print(f"    Tags removed:             {len(tag_removals)}")
    print()
    print(f"  Cleanup actions across all files:")
    print(f"    Duplicate frames removed: {len(dupe_removals)}")
    print(f"    ID3v1 tags removed:       {len(id3v1_removed)}")
    print(f"    ID3v2 version converted:  {len(id3v2_converted)}")

    if errored:
        print()
        print("  Failed Files:")
        for r in errored:
            print(f"    {r['filename']}: {r.get('error', 'Unknown error')}")

    print("=" * 60)


def print_restore_summary(results):
    """
    Print a summary of all restored tags.

    Args:
        results (list): List of dicts containing per-file restore results
    """
    total           = len(results)
    restored        = [r for r in results if r["status"] == "restored"]
    skipped         = [r for r in results if r["status"] == "skipped"]
    errored         = [r for r in results if r["status"] == "error"]
    album_restores  = [r for r in restored if r.get("album_restored")]
    title_restores  = [r for r in restored if r.get("title_restored")]
    artist_restores = [r for r in restored if r.get("artist_restored")]
    dupe_removals   = [r for r in results  if r.get("duplicates_removed")]
    id3v1_removed   = [r for r in results  if r.get("id3v1_removed")]
    id3v2_converted = [r for r in results  if r.get("id3v2_converted")]

    print("\n" + "=" * 60)
    print("RESTORE SUMMARY")
    print("=" * 60)
    print(f"  Total files processed:      {total}")
    print(f"  Files restored:             {len(restored)}")
    print(f"  Files skipped:              {len(skipped)}")
    print(f"  Files with errors:          {len(errored)}")
    print()
    print(f"  Tag restores across all files:")
    print(f"    Album restored:           {len(album_restores)}")
    print(f"    Title restored:           {len(title_restores)}")
    print(f"    Artist restored:          {len(artist_restores)}")
    print()
    print(f"  Cleanup actions across all files:")
    print(f"    Duplicate frames removed: {len(dupe_removals)}")
    print(f"    ID3v1 tags removed:       {len(id3v1_removed)}")
    print(f"    ID3v2 version converted:  {len(id3v2_converted)}")

    if errored:
        print()
        print("  Failed Files:")
        for r in errored:
            print(f"    {r['filename']}: {r.get('error', 'Unknown error')}")

    print("=" * 60)


def restore_tags(
    directory,
    restore_album=False,
    restore_title=False,
    restore_artist=False,
    original_album_tag_name="OriginalAlbum",
    original_title_tag_name="OriginalTitle",
    original_artist_tag_name="OriginalArtist",
    cleanup_options=None
):
    """
    Restore original tags from the TXXX backup tags.

    Args:
        directory (str): Path to the directory containing MP3 files
        restore_album (bool): Whether to restore the original album tag
        restore_title (bool): Whether to restore the original title tag
        restore_artist (bool): Whether to restore the original artist tag
        original_album_tag_name (str): Name of the TXXX tag storing the original album
        original_title_tag_name (str): Name of the TXXX tag storing the original title
        original_artist_tag_name (str): Name of the TXXX tag storing the original artist
        cleanup_options (dict): Dict of cleanup options
    """

    from mutagen.id3 import ID3, TALB, TIT2, TPE1, ID3NoHeaderError

    if cleanup_options is None:
        cleanup_options = {
            "remove_id3v1":      True,
            "use_id3v23":        True,
            "remove_duplicates": True,
        }

    # Verify the directory exists
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' not found.")
        return

    # Get all MP3 files in the directory
    mp3_files = [f for f in os.listdir(directory) if f.lower().endswith('.mp3')]

    if not mp3_files:
        print(f"No MP3 files found in '{directory}'.")
        return

    print(f"Found {len(mp3_files)} MP3 file(s) in '{directory}'.")
    print(f"Restoring Album:         {restore_album}")
    print(f"Restoring Title:         {restore_title}")
    print(f"Restoring Artist:        {restore_artist}")
    print(f"Remove ID3v1:            {cleanup_options['remove_id3v1']}")
    print(f"Use ID3v2.3:             {cleanup_options['use_id3v23']}")
    print(f"Remove Duplicate Frames: {cleanup_options['remove_duplicates']}\n")

    results = []

    for filename in mp3_files:
        filepath = os.path.join(directory, filename)
        print(f"Processing: '{filename}'")

        result = {"filename": filename}

        try:
            try:
                tags = ID3(filepath)
            except ID3NoHeaderError:
                print(f"  [WARN] No ID3 tags found in '{filename}'. Skipping.")
                result["status"]       = "skipped"
                result["skip_reasons"] = ["No ID3 tags found"]
                results.append(result)
                continue

            # Build original tag keys
            original_album_tag_key  = f"TXXX:{original_album_tag_name}"
            original_title_tag_key  = f"TXXX:{original_title_tag_name}"
            original_artist_tag_key = f"TXXX:{original_artist_tag_name}"

            any_restored = False
            skip_reasons = []

            # --- Restore Album ---
            if restore_album:
                if original_album_tag_key in tags:
                    original_album = str(tags[original_album_tag_key])
                    current_album  = str(tags['TALB']) if 'TALB' in tags else 'N/A'
                    tags.add(TALB(encoding=3, text=original_album))
                    result["album_restored"] = True
                    result["old_album"]      = current_album
                    result["new_album"]      = original_album
                    any_restored = True
                    print(f"  [OK] Restoring album: '{current_album}' -> '{original_album}'")
                else:
                    skip_reasons.append(f"Album:  no '{original_album_tag_name}' tag found")
                    print(f"  [SKIP] No '{original_album_tag_name}' tag found. Cannot restore album.")

            # --- Restore Title ---
            if restore_title:
                if original_title_tag_key in tags:
                    original_title = str(tags[original_title_tag_key])
                    current_title  = str(tags['TIT2']) if 'TIT2' in tags else 'N/A'
                    tags.add(TIT2(encoding=3, text=original_title))
                    result["title_restored"] = True
                    result["old_title"]      = current_title
                    result["new_title"]      = original_title
                    any_restored = True
                    print(f"  [OK] Restoring title: '{current_title}' -> '{original_title}'")
                else:
                    skip_reasons.append(f"Title:  no '{original_title_tag_name}' tag found")
                    print(f"  [SKIP] No '{original_title_tag_name}' tag found. Cannot restore title.")

            # --- Restore Artist ---
            if restore_artist:
                if original_artist_tag_key in tags:
                    original_artist = str(tags[original_artist_tag_key])
                    current_artist  = str(tags['TPE1']) if 'TPE1' in tags else 'N/A'
                    tags.add(TPE1(encoding=3, text=original_artist))
                    result["artist_restored"] = True
                    result["old_artist"]      = current_artist
                    result["new_artist"]      = original_artist
                    any_restored = True
                    print(f"  [OK] Restoring artist: '{current_artist}' -> '{original_artist}'")
                else:
                    skip_reasons.append(f"Artist: no '{original_artist_tag_name}' tag found")
                    print(f"  [SKIP] No '{original_artist_tag_name}' tag found. Cannot restore artist.")

            # --- Apply Cleanup and Save ---
            cleanup_actions          = apply_cleanup(tags, filepath, cleanup_options)
            result["duplicates_removed"] = any("Removed duplicate" in a for a in cleanup_actions)
            result["id3v1_removed"]      = any("Removed ID3v1"     in a for a in cleanup_actions)
            result["id3v2_converted"]    = any("Converted"         in a for a in cleanup_actions)

            if any_restored:
                result["status"] = "restored"
            else:
                result["status"]       = "skipped"
                result["skip_reasons"] = skip_reasons

        except Exception as e:
            print(f"  [ERROR] Failed to restore '{filename}': {e}")
            result["status"] = "error"
            result["error"]  = str(e)

        results.append(result)
        print()

    print_restore_summary(results)


def update_album_tags(
    directory,
    new_album_name,
    original_album_tag_name="OriginalAlbum",
    original_title_tag_name="OriginalTitle",
    original_artist_tag_name="OriginalArtist",
    new_artist_name="Various",
    cleanup_options=None
):
    """
    Update the Album tag for all MP3 files in a directory.
    The original album name is stored in a custom TXXX tag.
    The original title is stored in a custom TXXX tag.
    The original artist is stored in a custom TXXX tag.
    Removes all tags except: Title, Artist, Album, Length, Date, Album Artist.
    Updates Title to format: "Artist Name - Title"
    Updates Artist to "Various"

    Args:
        directory (str): Path to the directory containing MP3 files
        new_album_name (str): New album name to set
        original_album_tag_name (str): Name of the custom tag to store the original album name
        original_title_tag_name (str): Name of the custom tag to store the original title
        original_artist_tag_name (str): Name of the custom tag to store the original artist
        new_artist_name (str): New artist name to set (default: "Various")
        cleanup_options (dict): Dict of cleanup options
    """

    from mutagen.id3 import ID3, TALB, TXXX, TIT2, TPE1, ID3NoHeaderError

    if cleanup_options is None:
        cleanup_options = {
            "remove_id3v1":      True,
            "use_id3v23":        True,
            "remove_duplicates": True,
        }

    # Tags to keep
    # TIT2 = Title, TPE1 = Artist, TALB = Album, TLEN = Length,
    # TDRC = Date, TPE2 = Album Artist
    TAGS_TO_KEEP = {'TIT2', 'TPE1', 'TALB', 'TLEN', 'TDRC', 'TPE2'}

    # Verify the directory exists
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' not found.")
        return

    # Get all MP3 files in the directory
    mp3_files = [f for f in os.listdir(directory) if f.lower().endswith('.mp3')]

    if not mp3_files:
        print(f"No MP3 files found in '{directory}'.")
        return

    print(f"Found {len(mp3_files)} MP3 file(s) in '{directory}'.")
    print(f"New Album Name:          {new_album_name}")
    print(f"New Artist Name:         {new_artist_name}")
    print(f"Original Album Tag:      {original_album_tag_name}")
    print(f"Original Title Tag:      {original_title_tag_name}")
    print(f"Original Artist Tag:     {original_artist_tag_name}")
    print(f"Keeping Tags:            {', '.join(TAGS_TO_KEEP)}")
    print(f"Remove ID3v1:            {cleanup_options['remove_id3v1']}")
    print(f"Use ID3v2.3:             {cleanup_options['use_id3v23']}")
    print(f"Remove Duplicate Frames: {cleanup_options['remove_duplicates']}\n")

    results = []

    for filename in mp3_files:
        filepath = os.path.join(directory, filename)
        print(f"Processing: '{filename}'")

        result = {"filename": filename}

        try:
            # Try to load existing ID3 tags
            try:
                tags = ID3(filepath)
            except ID3NoHeaderError:
                tags = ID3()
                print(f"  [INFO] No ID3 header found. Creating new tags.")

            # Get the current values (if they exist)
            current_album  = str(tags['TALB']) if 'TALB' in tags else None
            current_title  = str(tags['TIT2']) if 'TIT2' in tags else None
            current_artist = str(tags['TPE1']) if 'TPE1' in tags else None

            # Build the original tag keys
            original_album_tag_key  = f"TXXX:{original_album_tag_name}"
            original_title_tag_key  = f"TXXX:{original_title_tag_name}"
            original_artist_tag_key = f"TXXX:{original_artist_tag_name}"

            # --- Save Original Tags (only if they don't already exist) ---
            # save_original_tag() returns the protected original value,
            # whether it was just saved or already existed.
            original_album  = save_original_tag(tags, original_album_tag_key,  original_album_tag_name,  current_album,  "album")
            original_title  = save_original_tag(tags, original_title_tag_key,  original_title_tag_name,  current_title,  "title")
            original_artist = save_original_tag(tags, original_artist_tag_key, original_artist_tag_name, current_artist, "artist")

            # --- Build New Title ---
            # Always built from the original artist and original title
            # to ensure correct format even on rerun
            new_title = build_new_title(original_artist, original_title)
            if new_title:
                if new_title == current_title:
                    print(f"  [SKIP] Title already correct: '{current_title}'.")
                else:
                    print(f"  [INFO] Updating title: '{current_title}' -> '{new_title}'")
            else:
                print(f"  [WARN] Could not build new title. Skipping title update.")

            # --- Remove Unwanted Tags ---
            tags_to_remove = [
                key for key in tags.keys()
                if key[:4] not in TAGS_TO_KEEP
                and key != original_album_tag_key
                and key != original_title_tag_key
                and key != original_artist_tag_key
            ]

            if tags_to_remove:
                print(f"  [INFO] Removing tags: {', '.join(tags_to_remove)}")
                for tag in tags_to_remove:
                    del tags[tag]
            else:
                print(f"  [INFO] No extra tags to remove.")

            # --- Update Album Tag ---
            tags.add(TALB(encoding=3, text=new_album_name))

            # --- Update Title Tag ---
            if new_title:
                tags.add(TIT2(encoding=3, text=new_title))

            # --- Update Artist Tag ---
            tags.add(TPE1(encoding=3, text=new_artist_name))

            # --- Apply Cleanup and Save ---
            # Note: apply_cleanup() handles saving the file,
            # so we don't call tags.save() separately
            cleanup_actions              = apply_cleanup(tags, filepath, cleanup_options)
            result["duplicates_removed"] = any("Removed duplicate" in a for a in cleanup_actions)
            result["id3v1_removed"]      = any("Removed ID3v1"     in a for a in cleanup_actions)
            result["id3v2_converted"]    = any("Converted"         in a for a in cleanup_actions)

            # --- Track Changes for Summary ---
            album_changed  = current_album  != new_album_name
            title_changed  = current_title  != new_title
            artist_changed = current_artist != new_artist_name
            any_changed    = album_changed or title_changed or artist_changed or bool(tags_to_remove)

            result["status"]         = "updated" if any_changed else "skipped"
            result["old_album"]      = current_album   or "N/A"
            result["new_album"]      = new_album_name
            result["old_title"]      = current_title   or "N/A"
            result["new_title"]      = new_title       or "N/A"
            result["old_artist"]     = current_artist  or "N/A"
            result["new_artist"]     = new_artist_name
            result["album_changed"]  = album_changed
            result["title_changed"]  = title_changed
            result["artist_changed"] = artist_changed
            result["tags_removed"]   = tags_to_remove if tags_to_remove else None

            print(f"  [OK] {'Updated' if any_changed else 'No changes to'} '{filename}'")

        except Exception as e:
            print(f"  [ERROR] Failed to update '{filename}': {e}")
            result["status"] = "error"
            result["error"]  = str(e)

        results.append(result)
        print()

    print_summary(results)


if __name__ == "__main__":
    main()