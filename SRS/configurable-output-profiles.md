# SRS: Configurable Output Profiles

**Version:** 1.0  |  **Date:** 2026-02-22  |  **Status:** Implemented

---

## 1. Purpose

Move output-type profile definitions from hardcoded Python dataclasses into `config.yaml`, enabling users to create, modify, and delete output profiles without editing source code. The two built-in profiles (`ride-command` and `basic`) become seed defaults that are written to `config.yaml` on first run, and all profile resolution thereafter reads from the config file.

---

## 2. Requirements

### 2.1 Profile Definition in config.yaml

Output profiles shall be defined under a top-level `output_types` key in `config.yaml`:

```yaml
settings:
  output_type: ride-command
  usb_dir: RZR/Music
  workers: 6

output_types:
  ride-command:
    description: "Polaris Ride Command infotainment system"
    directory_structure: flat
    filename_format: full
    id3_version: 3
    strip_id3v1: true
    title_tag_format: artist_title
    artwork_size: 100
    quality_preset: lossless
    pipeline_album: playlist_name
    pipeline_artist: various

  basic:
    description: "Standard MP3 with original tags and artwork"
    directory_structure: flat
    filename_format: full
    id3_version: 4
    strip_id3v1: true
    title_tag_format: artist_title
    artwork_size: 0
    quality_preset: lossless
    pipeline_album: original
    pipeline_artist: original

playlists:
  - key: Pop_Workout
    url: https://music.apple.com/us/playlist/...
    name: Pop Workout
```

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | | [x] | Profiles defined under `output_types` key in `config.yaml` as a YAML mapping of profile-name → field values |
| 2.1.2 | | [x] | Each profile entry contains all `OutputProfile` fields except `name` (derived from the YAML key) |
| 2.1.3 | | [x] | Field names in YAML use snake_case matching the `OutputProfile` dataclass (e.g., `directory_structure`, `id3_version`) |
| 2.1.4 | | [x] | YAML types map naturally: strings for text fields, integers for `id3_version` and `artwork_size`, booleans for `strip_id3v1` |

### 2.2 Seed Defaults

On first run or when `output_types` is absent from `config.yaml`, the system shall generate the section from built-in defaults:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | | [x] | Built-in defaults for `ride-command` and `basic` profiles defined as a constant (e.g., `DEFAULT_OUTPUT_PROFILES`) in source code |
| 2.2.2 | | [x] | `ConfigManager._create_default()` includes the `output_types` section with both built-in profiles |
| 2.2.3 | | [x] | When loading an existing `config.yaml` that has no `output_types` key, the built-in defaults are written to the file (automatic migration) |
| 2.2.4 | | [x] | Migration preserves all other existing config.yaml content (settings, playlists) |
| 2.2.5 | | [x] | After migration, the system reads profiles from config.yaml — not from built-in defaults |

### 2.3 Profile Loading

`ConfigManager` shall load profiles from `config.yaml` and construct `OutputProfile` dataclass instances:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | | [x] | `_load_yaml()` parses the `output_types` mapping and builds `OutputProfile` instances |
| 2.3.2 | | [x] | Loaded profiles stored in a dictionary accessible via `ConfigManager` (e.g., `config.output_profiles`) |
| 2.3.3 | | [x] | The module-level `OUTPUT_PROFILES` dictionary is populated from `ConfigManager` at startup (not from hardcoded definitions) |
| 2.3.4 | | [x] | `settings.output_type` must reference a profile name that exists in `output_types`; invalid references produce a clear error listing available profiles |

### 2.4 Profile Validation

All profile fields shall be validated when loading from config.yaml:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | | [x] | Missing required fields produce a clear error naming the profile and missing field |
| 2.4.2 | | [x] | `directory_structure` validated against `VALID_DIR_STRUCTURES` |
| 2.4.3 | | [x] | `filename_format` validated against `VALID_FILENAME_FORMATS` |
| 2.4.4 | | [x] | `id3_version` validated: must be `3` or `4` |
| 2.4.5 | | [x] | `strip_id3v1` validated: must be boolean |
| 2.4.6 | | [x] | `title_tag_format` validated: must be `"artist_title"` (currently the only supported value) |
| 2.4.7 | | [x] | `artwork_size` validated: must be integer (`-1`, `0`, or positive) |
| 2.4.8 | | [x] | `quality_preset` validated against `QUALITY_PRESETS` keys (`lossless`, `high`, `medium`, `low`) |
| 2.4.9 | | [x] | `pipeline_album` validated: must be `"playlist_name"` or `"original"` |
| 2.4.10 | | [x] | `pipeline_artist` validated: must be `"various"` or `"original"` |
| 2.4.11 | | [x] | `description` validated: must be a non-empty string |
| 2.4.12 | | [x] | Validation errors include the profile name and field name for easy debugging |
| 2.4.13 | | [x] | All validation runs at startup; invalid profiles halt the program with a non-zero exit code |

### 2.5 User-Defined Profiles

Users shall be able to add new profiles by editing `config.yaml`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | | [x] | New profiles added under `output_types` are automatically available at next startup |
| 2.5.2 | | [x] | New profile names appear in `--output-type` CLI flag choices |
| 2.5.3 | | [x] | New profiles appear in interactive menu's "Change output profile" (P) list |
| 2.5.4 | | [x] | New profiles create their own export directory: `export/<profile-name>/` |
| 2.5.5 | | [x] | Profile names validated: lowercase alphanumeric and hyphens only (e.g., `my-device`, `car-stereo`) |
| 2.5.6 | | [x] | Invalid profile names rejected with clear error at startup |

### 2.6 Modifying Built-in Profiles

Users shall be able to customize the built-in profiles by editing their values in `config.yaml`:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | | [x] | Users can change any field of `ride-command` or `basic` profiles in config.yaml |
| 2.6.2 | | [x] | Modified built-in profiles are loaded with the user's values (not overwritten by defaults) |
| 2.6.3 | | [x] | Deleting a built-in profile from config.yaml is allowed — it will not be re-created on next run |

### 2.7 Removing Hardcoded Profiles

The hardcoded `OUTPUT_PROFILES` dictionary in source code shall be replaced:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | | [x] | The hardcoded `OUTPUT_PROFILES` dictionary is removed from `porter_core.py` |
| 2.7.2 | | [x] | A `DEFAULT_OUTPUT_PROFILES` constant retains the two built-in profile definitions as seed data only (used for migration and `_create_default()`) |
| 2.7.3 | | [x] | All code that previously read from `OUTPUT_PROFILES` now reads from `ConfigManager`'s loaded profiles |
| 2.7.4 | | [x] | The `OutputProfile` dataclass remains unchanged in source code |

### 2.8 Interactive Menu Updates

The interactive menu profile selection (P option) shall reflect config-defined profiles:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.8.1 | | [x] | "Change output profile" lists all profiles from config.yaml (not just hardcoded ones) |
| 2.8.2 | | [x] | Profile selection persists to `settings.output_type` in config.yaml (existing behavior) |
| 2.8.3 | | [x] | Profile descriptions displayed alongside names in selection menu |

### 2.9 CLI Updates

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.9.1 | | [x] | `--output-type` flag dynamically accepts any profile name from config.yaml |
| 2.9.2 | | [x] | `--help` output for `--output-type` lists available profiles from config.yaml |
| 2.9.3 | | [x] | Invalid `--output-type` value produces clear error listing available profiles |
| 2.9.4 | | [x] | Profile override via `dataclasses.replace()` continues to work for CLI flag overrides (existing behavior) |

### 2.10 Web Dashboard Updates

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.10.1 | | [x] | `GET /api/settings` returns all profiles from config.yaml (not hardcoded) |
| 2.10.2 | | [x] | Settings page profile comparison table shows all config-defined profiles |
| 2.10.3 | | [x] | Profile selection dropdowns in pipeline/convert pages reflect config-defined profiles |

### 2.11 Startup Banner

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.11.1 | | [x] | Startup banner continues to display active profile name and description |
| 2.11.2 | | [x] | Total available profiles count shown (e.g., `Profile: ride-command (1 of 3)`) |

### 2.12 Config Persistence

Profile changes made through the application shall be saved back to config.yaml:

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.12.1 | | [x] | `ConfigManager._save()` writes the `output_types` section back to YAML preserving user-defined profiles |
| 2.12.2 | | [x] | Round-trip fidelity: load → save produces equivalent YAML (no data loss or reordering) |
| 2.12.3 | | [x] | YAML comments in config.yaml are not preserved (PyYAML limitation — document this) |

### 2.13 Backward Compatibility

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.13.1 | | [x] | Existing `config.yaml` files without `output_types` are automatically migrated (see 2.2.3) |
| 2.13.2 | | [x] | After migration, behavior is identical to the current hardcoded profiles (zero regression) |
| 2.13.3 | | [x] | `settings.output_type` continues to work as before — no changes to the settings key name |
| 2.13.4 | | [x] | Profile-scoped export directories (`export/<profile>/`) continue to work unchanged |
| 2.13.5 | | [x] | All CLI flags (`--output-type`, `--dir-structure`, `--filename-format`, `--preset`) continue to work unchanged |

### 2.14 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.14.1 | | [x] | Empty `output_types` mapping (`output_types: {}`): error — at least one profile required |
| 2.14.2 | | [x] | `output_types` key present but value is `null`: treated as missing, triggers migration from defaults |
| 2.14.3 | | [x] | `settings.output_type` references a deleted profile: error at startup listing available profiles |
| 2.14.4 | | [x] | Profile with unknown extra fields: ignored (forward compatibility — new fields in future versions won't break older configs) |
| 2.14.5 | | [x] | Duplicate profile names: impossible in YAML (last-key-wins per YAML spec) — no special handling needed |
| 2.14.6 | | [x] | Profile name with spaces or special characters: rejected by name validation (2.5.5) with suggestion to use hyphens |
| 2.14.7 | | [x] | config.yaml with only one profile: valid — system operates normally with a single profile |
