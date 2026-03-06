"""
core.tagging - TagApplicator: builds and applies ID3 tags from profile templates.
"""
from __future__ import annotations

import io
from pathlib import Path

from core.constants import (
    APIC_MIME_JPEG,
    APIC_MIME_PNG,
    APIC_TYPE_FRONT_COVER,
)
from core.utils import apply_template, resize_cover_art_bytes, sanitize_filename

# Third-party imports (mutagen) — set by _init_third_party()
_ID3 = None
_TIT2 = _TPE1 = _TALB = _TCON = _TRCK = _TPOS = _TDRC = _TCOM = None
_TPE2 = _TBPM = _COMM = _USLT = _TCOP = _TIT1 = _TCMP = _APIC = _TXXX = None
_ID3NoHeaderError = None
_Encoding = None
_mutagen_mp3 = None

ID3V2_HEADER_SIZE = 10        # Fixed 10-byte ID3v2 header prefix
IO_CHUNK_SIZE = 65536         # Read/write chunk size for file I/O
_SYNCSAFE_SHIFTS = (21, 14, 7, 0)  # Bit shifts for ID3v2 syncsafe integer decode


class TagApplicator:
    """Applies profile-specific ID3 tags to clean library MP3s on-the-fly.

    Library MP3s contain only a TXXX:TrackUUID identifier.  This class
    reads track metadata from TrackDB and applies profile-driven tags
    (title, artist, album, genre, id3_extra, cover art) either:
    - As a streaming response (build_tagged_stream) for HTTP serving
    - As a file copy (apply_tags_to_file) for physical sync
    """

    # Mapping of ID3v2 frame ID prefixes to mutagen constructors.
    # Populated lazily on first use to avoid import at module level.
    _frame_constructors = None

    def __init__(self, track_db, project_root='.'):
        self.track_db = track_db
        self.project_root = Path(project_root)

    @classmethod
    def _get_frame_constructors(cls):
        """Lazy-init frame constructor mapping."""
        if cls._frame_constructors is None:
            from mutagen.id3 import COMM, TXXX  # type: ignore[attr-defined]
            cls._frame_constructors = {
                'TXXX': TXXX,
                'COMM': COMM,
            }
        return cls._frame_constructors

    def _resolve_template_vars(self, track_meta, playlist_name):
        """Build template variable dict from track metadata."""
        return {
            'title': track_meta.get('title', ''),
            'artist': track_meta.get('artist', ''),
            'album': track_meta.get('album', ''),
            'genre': track_meta.get('genre') or '',
            'track_number': str(track_meta.get('track_number') or ''),
            'track_total': str(track_meta.get('track_total') or ''),
            'disc_number': str(track_meta.get('disc_number') or ''),
            'disc_total': str(track_meta.get('disc_total') or ''),
            'year': track_meta.get('year') or '',
            'composer': track_meta.get('composer') or '',
            'album_artist': track_meta.get('album_artist') or '',
            'bpm': str(track_meta.get('bpm') or ''),
            'comment': track_meta.get('comment') or '',
            'compilation': '1' if track_meta.get('compilation') else '',
            'grouping': track_meta.get('grouping') or '',
            'lyrics': track_meta.get('lyrics') or '',
            'copyright': track_meta.get('copyright') or '',
            'playlist': playlist_name,
            'playlist_key': track_meta.get('playlist', ''),
        }

    def _build_id3_tags(self, track_meta, profile, playlist_name):
        """Build a mutagen ID3 tag object with profile-specific tags.

        Returns (tags, v2_version, include_v1) tuple.
        """
        from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TXXX  # type: ignore[attr-defined]

        tvars = self._resolve_template_vars(track_meta, playlist_name)

        tags = ID3()

        # Primary tag templates
        tags["TIT2"] = TIT2(encoding=3,
                            text=apply_template(profile.id3_title, **tvars))
        tags["TPE1"] = TPE1(encoding=3,
                            text=apply_template(profile.id3_artist, **tvars))
        tags["TALB"] = TALB(encoding=3,
                            text=apply_template(profile.id3_album, **tvars))

        # Genre tag (TCON) — only add if non-empty
        if profile.id3_genre:
            from mutagen.id3 import TCON  # type: ignore[attr-defined]
            tags["TCON"] = TCON(encoding=3,
                                text=apply_template(profile.id3_genre, **tvars))

        # Extra tags (arbitrary ID3 frames from profile)
        primary_frames = {'TIT2', 'TPE1', 'TALB', 'TCON'}
        for frame_id, value_template in profile.id3_extra.items():
            if frame_id in primary_frames:
                continue  # Primary fields take precedence
            value = apply_template(value_template, **tvars)
            if not value:
                continue  # Empty string = omit frame

            if frame_id.startswith('TXXX:'):
                desc = frame_id[5:]  # Strip "TXXX:" prefix
                tags.add(TXXX(encoding=3, desc=desc, text=[value]))
            elif frame_id == 'COMM':
                constructors = self._get_frame_constructors()
                tags.add(constructors['COMM'](
                    encoding=3, lang='eng', desc='', text=[value]))
            elif frame_id.startswith('T'):
                # Generic text frame (TCON, TPE2, TRCK, TDRC, etc.)
                from mutagen.id3 import Frames
                frame_cls = Frames.get(frame_id)
                if frame_cls:
                    tags[frame_id] = frame_cls(encoding=3, text=value)

        # Cover art
        cover_art_path = track_meta.get('cover_art_path')
        if cover_art_path and profile.artwork_size != -1:
            full_art_path = self.project_root / cover_art_path
            if full_art_path.exists():
                art_data = full_art_path.read_bytes()
                art_mime = (APIC_MIME_PNG if cover_art_path.endswith('.png')
                            else APIC_MIME_JPEG)
                if profile.artwork_size > 0:
                    art_data, art_mime = resize_cover_art_bytes(
                        art_data, profile.artwork_size, art_mime)
                tags.add(APIC(
                    encoding=3,
                    mime=art_mime,
                    type=APIC_TYPE_FRONT_COVER,
                    desc='Cover',
                    data=art_data,
                ))

        # Determine ID3 version settings from profile.id3_versions
        v2_version = 4  # default
        include_v1 = False
        for v in profile.id3_versions:
            if v == 'v2.3':
                v2_version = 3
            elif v == 'v2.4':
                v2_version = 4
            elif v == 'v1':
                include_v1 = True

        return tags, v2_version, include_v1

    def _find_audio_offset(self, mp3_path):
        """Find where audio data starts in an MP3 file (after ID3v2 header).

        Returns the byte offset of the first audio frame.
        """
        with open(mp3_path, 'rb') as f:
            header = f.read(10)
            if len(header) < 10 or header[:3] != b'ID3':
                return 0  # No ID3v2 header — audio starts at byte 0

            # ID3v2 size is stored as a 4-byte syncsafe integer (bytes 6-9)
            size_bytes = header[6:10]
            tag_size = sum(
                size_bytes[i] << shift
                for i, shift in enumerate(_SYNCSAFE_SHIFTS)
            )
            # Total ID3v2 block = fixed 10-byte header + tag content size
            return ID3V2_HEADER_SIZE + tag_size

    def build_tagged_stream(self, mp3_path, track_meta, profile,
                            playlist_name):
        """Build components for streaming a tagged MP3.

        Returns (id3_bytes, audio_offset, total_size):
        - id3_bytes: Complete ID3v2 tag block as bytes
        - audio_offset: Where audio data starts in the clean MP3
        - total_size: Total size of the tagged MP3 stream
        """

        tags, v2_version, _include_v1 = self._build_id3_tags(
            track_meta, profile, playlist_name)

        # Render the ID3v2 tag to bytes
        tag_buf = io.BytesIO()
        tags.save(tag_buf, v2_version=v2_version, v1=0)
        id3_bytes = tag_buf.getvalue()

        # Find where audio starts in the clean MP3
        audio_offset = self._find_audio_offset(mp3_path)

        # Total size = new tags + raw audio
        file_size = Path(mp3_path).stat().st_size
        audio_size = file_size - audio_offset
        total_size = len(id3_bytes) + audio_size

        return id3_bytes, audio_offset, total_size

    def apply_tags_to_file(self, mp3_path, track_meta, profile,
                           playlist_name, output_path):
        """Write a fully-tagged copy of the MP3 to output_path.

        Used during physical sync to create profile-specific copies.
        """
        tags, v2_version, include_v1 = self._build_id3_tags(
            track_meta, profile, playlist_name)

        audio_offset = self._find_audio_offset(mp3_path)

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        tag_buf = io.BytesIO()
        tags.save(tag_buf, v2_version=v2_version,
                  v1=1 if include_v1 else 0)
        tag_bytes = tag_buf.getvalue()

        with open(output_path, 'wb') as out:
            out.write(tag_bytes)
            with open(mp3_path, 'rb') as src:
                src.seek(audio_offset)
                while True:
                    chunk = src.read(IO_CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)

    def build_output_filename(self, track_meta, profile, playlist_name):
        """Build destination filename using the profile's filename template."""
        tvars = self._resolve_template_vars(track_meta, playlist_name)
        name = apply_template(profile.filename, **tvars)
        return sanitize_filename(name) + '.mp3'

    def build_output_subdir(self, track_meta, profile, playlist_name):
        """Build destination subdirectory using the profile's directory template.

        Returns empty string for flat output.
        """
        if not profile.directory:
            return ''
        tvars = self._resolve_template_vars(track_meta, playlist_name)
        subdir = apply_template(profile.directory, **tvars)
        # Sanitize each path component
        parts = subdir.split('/')
        return '/'.join(sanitize_filename(p) for p in parts if p)


