# SRS: Service Layer — Business Logic / Interface Separation

**Version:** 1.0  |  **Date:** 2026-02-21  |  **Status:** Draft

---

## 1. Purpose

Decouple the `music-porter` business logic from all user interface concerns — console `print()` output, `input()` prompts, and progress bars — so that the same core classes can be driven by the CLI, the Interactive CLI menu, and the Web dashboard without modification. Business logic classes shall return structured result objects and accept callback functions for user interaction, never directly reading from stdin or writing to stdout.

---

## 2. Requirements

### 2.1 Service Layer Architecture

Each business logic class shall return structured result objects instead of printing summaries directly. All operations that currently call `_print_*_summary()` internally shall instead populate a result/statistics object and return it to the caller. The caller (CLI, Interactive Menu, or Web handler) is responsible for presenting results.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.1 | | [x] | Every public method on a business logic class (`TaggerManager`, `Converter`, `Downloader`, `CookieManager`, `USBManager`, `SummaryManager`, `CoverArtManager`, `PipelineOrchestrator`) shall return a structured result object (dataclass or typed dict) containing all data currently printed in its summary |
| 2.1.2 | | [x] | No business logic class shall call `print()` for summary display. All `_print_*_summary()` methods shall be removed from the business logic classes and replaced with result object population |
| 2.1.3 | | [x] | No business logic class shall call `input()`. All user interaction shall be delegated through callback interfaces (see 2.2) |
| 2.1.4 | | [x] | Business logic classes shall accept an optional `Logger` instance (as today) but shall not assume that logging implies console output — `Logger` continues to write to log files and may optionally echo to console at the caller's discretion |
| 2.1.5 | | [x] | Existing `*Statistics` classes (`TagStatistics`, `ConversionStatistics`, `DownloadStatistics`, `PipelineStatistics`, `AggregateStatistics`, `LibrarySummaryStatistics`) shall continue to serve as the structured result objects — they already track the data, but callers shall now receive them as return values rather than having the business class print them |

#### 2.1.6 Result Objects

Each operation shall return a result object. The following table defines the minimum fields per result type. Fields marked "(existing)" are already tracked in the corresponding `*Statistics` class; fields marked "(new)" must be added.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.1.6 | | [x] | `TaggerManager.update_tags()` shall return a `TagUpdateResult` containing: `success: bool`, `directory: str`, `duration: float`, `files_processed: int`, `files_updated: int`, `files_skipped: int`, `errors: int`, `title_updated: int` (existing), `album_updated: int` (existing), `artist_updated: int` (existing), `title_stored: int` (existing), `artist_stored: int` (existing), `album_stored: int` (existing) |
| 2.1.7 | | [x] | `TaggerManager.restore_tags()` shall return a `TagRestoreResult` containing: `success: bool`, `directory: str`, `duration: float`, `files_processed: int`, `files_restored: int`, `files_skipped: int`, `errors: int`, `title_restored: int` (existing), `artist_restored: int` (existing), `album_restored: int` (existing) |
| 2.1.8 | | [x] | `TaggerManager.reset_tags_from_source()` shall return a `TagResetResult` containing: `success: bool`, `input_dir: str`, `output_dir: str`, `duration: float`, `files_matched: int`, `files_reset: int`, `files_skipped: int`, `errors: int` |
| 2.1.9 | | [x] | `Converter.convert()` shall return a `ConversionResult` containing: `success: bool`, `input_dir: str`, `output_dir: str`, `duration: float`, `quality_preset: str`, `quality_mode: str`, `quality_value: str`, `workers: int`, `total_found: int` (existing), `converted: int` (existing), `overwritten: int` (existing), `skipped: int` (existing), `errors: int` (existing) |
| 2.1.10 | | [x] | `Downloader.download()` shall return a `DownloadResult` containing: `success: bool`, `key: str`, `album_name: str`, `duration: float`, `playlist_total: int` (existing), `downloaded: int` (existing), `skipped: int` (existing), `failed: int` (existing) |
| 2.1.11 | | [x] | `USBManager.sync_to_usb()` shall return a `USBSyncResult` containing: `success: bool`, `source: str`, `destination: str`, `volume_name: str`, `duration: float`, `files_found: int` (existing), `files_copied: int` (existing), `files_skipped: int` (existing), `files_failed: int` (existing) |
| 2.1.12 | | [x] | `SummaryManager.generate_summary()` shall return a `LibrarySummaryResult` containing: `success: bool`, `export_dir: str`, `scan_duration: float`, `mode: str` (quick/default/detailed), `total_playlists: int`, `total_files: int`, `total_size_bytes: int`, `avg_file_size: float`, `files_with_protection_tags: int`, `files_missing_protection_tags: int`, `sample_size: int`, `files_with_cover_art: int`, `files_without_cover_art: int`, `files_with_original_cover_art: int`, `files_with_resized_cover_art: int`, `playlist_summaries: list[PlaylistSummary]` |
| 2.1.13 | | [x] | `CoverArtManager` action methods (`embed()`, `extract()`, `update()`, `strip()`) shall each return a `CoverArtResult` containing: `success: bool`, `action: str`, `directory: str`, `duration: float`, `files_processed: int`, `files_modified: int`, `files_skipped: int`, `errors: int` |
| 2.1.14 | | [x] | `PipelineOrchestrator.run_pipeline()` shall return a `PipelineResult` containing: `success: bool`, `playlist_name: str`, `playlist_key: str`, `duration: float`, `stages_completed: list[str]`, `stages_failed: list[str]`, `stages_skipped: list[str]`, plus nested results: `download_result: DownloadResult | None`, `conversion_result: ConversionResult | None`, `tag_result: TagUpdateResult | None`, `cover_art_result: CoverArtResult | None`, `usb_result: USBSyncResult | None` |
| 2.1.15 | | [x] | `PipelineOrchestrator.run_batch()` (or equivalent batch method) shall return an `AggregateResult` containing: `success: bool`, `duration: float`, `total_playlists: int`, `successful_playlists: int`, `failed_playlists: int`, `playlist_results: list[PipelineResult]`, `cumulative_stats: dict` (same shape as `AggregateStatistics.get_cumulative_stats()`) |

### 2.2 User Input Abstraction

All embedded `input()` calls in business logic classes shall be replaced with callback functions. Each class that currently prompts the user shall accept an optional `UserPromptHandler` (protocol/interface) at construction. When no handler is provided, the class shall use sensible non-interactive defaults (fail-safe: deny destructive actions, skip optional prompts).

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.1 | | [x] | A `UserPromptHandler` protocol shall define the following methods, each returning the user's response asynchronously or synchronously depending on the interface |
| 2.2.2 | | [x] | `confirm(message: str, default: bool) -> bool` — for yes/no confirmations. The `default` parameter indicates the default answer when the user provides no input. Used by: cookie refresh prompt (`default=True`), continue-without-cookies prompt (`default=False`), download confirmation (`default=False`), USB eject prompt (`default=False`), USB copy prompt (`default=False`), save-to-config prompt (`default=False`), embed-cover-art prompt (`default=True`), cover-art batch continue (`default=True`), dependency warning continue (`default=True`) |
| 2.2.3 | | [x] | `confirm_destructive(message: str) -> bool` — for destructive operations requiring explicit typed confirmation (e.g., `reset_tags_from_source` which currently requires typing "yes"). Non-interactive default: `False` (deny) |
| 2.2.4 | | [x] | `select_from_list(prompt: str, options: list[str], allow_cancel: bool) -> int | None` — for numbered menu selections. Returns 0-based index of selected option, or `None` if cancelled. Used by: USB drive selection, browser selection. Non-interactive default: `None` (cancel) |
| 2.2.5 | | [x] | `get_text_input(prompt: str, default: str | None) -> str | None` — for free-text input. Used by: URL entry, cover art resize dimension. Returns `None` if cancelled. Non-interactive default: return `default` |
| 2.2.6 | | [x] | `wait_for_continue(message: str) -> None` — for modal pauses that block until the user acknowledges (e.g., "Press Enter after logging in...", "Press Enter to continue..."). Non-interactive default: return immediately |
| 2.2.7 | | [x] | When no `UserPromptHandler` is provided (or `None`), business logic classes shall use a `NonInteractivePromptHandler` that returns fail-safe defaults: `confirm()` returns `default`, `confirm_destructive()` returns `False`, `select_from_list()` returns `None`, `get_text_input()` returns `default`, `wait_for_continue()` returns immediately |

#### 2.2.8 Input Call Migration Map

The following table maps every current `input()` call to the `UserPromptHandler` method that replaces it.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.2.8 | | [x] | `Downloader.download()` line ~2171 ("Attempt automatic cookie refresh? [Y/n]") shall call `prompt_handler.confirm(message, default=True)` |
| 2.2.9 | | [x] | `Downloader.download()` line ~2185 ("Continue without valid cookies? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 2.2.10 | | [x] | `Downloader.download()` line ~2191 ("Continue without valid cookies? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 2.2.11 | | [x] | `Downloader.download()` line ~2202 ("Download {key}? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 2.2.12 | | [x] | `CookieManager._extract_with_selenium()` line ~2587 ("Select browser [1]...") shall call `prompt_handler.select_from_list(prompt, browser_list, allow_cancel=True)` |
| 2.2.13 | | [x] | `CookieManager._extract_cookies_from_driver()` line ~2883 ("Press Enter after logging in...") shall call `prompt_handler.wait_for_continue(message)` |
| 2.2.14 | | [x] | `USBManager.select_usb_drive()` line ~3209 ("Select drive:") shall call `prompt_handler.select_from_list(prompt, drive_list, allow_cancel=True)` |
| 2.2.15 | | [x] | `USBManager._prompt_and_eject_usb()` line ~3413 ("Eject USB drive '{name}'? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 2.2.16 | | [x] | `TaggerManager.reset_tags_from_source()` line ~1534 ("Type 'yes' to continue...") shall call `prompt_handler.confirm_destructive(message)` |
| 2.2.17 | | [x] | `PipelineOrchestrator._ask_save_to_config()` line ~5044 ("Save '{album_name}' to config.yaml? [y/N]") shall call `prompt_handler.confirm(message, default=False)` |
| 2.2.18 | | [x] | `PipelineOrchestrator._check_and_embed_cover_art()` line ~5094 ("Embed cover art from source files? [Y/n]") shall call `prompt_handler.confirm(message, default=True)` |
| 2.2.19 | | [x] | `main()` cover-art batch confirmation prompts (lines ~6410, ~6476 — "Continue? [Y/n]" for batch cover-art operations on multiple directories) shall call `prompt_handler.confirm(message, default=True)` |

### 2.3 Progress & Display Abstraction

All embedded `print()` calls used for progress updates, status messages, and summary display during operations shall be routed through a `DisplayHandler` protocol. Business logic classes shall accept an optional `DisplayHandler` at construction. Summary rendering is the responsibility of the interface layer, not the business logic.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.1 | | [x] | A `DisplayHandler` protocol shall define the following methods for progress and status reporting during operations |
| 2.3.2 | | [x] | `show_progress(current: int, total: int, message: str) -> None` — replaces inline `print()` calls that report file-by-file progress during batch operations (e.g., "Converting file 3/50..."). CLI implements this with tqdm or line printing; Web implements with progress events |
| 2.3.3 | | [x] | `show_status(message: str, level: str) -> None` — replaces inline `print()` calls that report status messages (e.g., "Found 50 MP3 files", "Skipping existing file"). `level` is one of: `"info"`, `"success"`, `"warning"`, `"error"`. CLI implements with colored console output; Web implements with log events |
| 2.3.4 | | [x] | `show_banner(title: str, subtitle: str | None) -> None` — replaces the startup banner print block. CLI renders to console; Web may ignore or log it |
| 2.3.5 | | [x] | The existing `Logger` class shall continue to handle file logging independently of `DisplayHandler`. `Logger.info()`, `Logger.error()`, etc. always write to the log file. `DisplayHandler.show_status()` is for user-facing display, not log file writing |
| 2.3.6 | | [x] | When no `DisplayHandler` is provided (or `None`), business logic classes shall use a `NullDisplayHandler` that silently discards all display calls. Operations still log to the `Logger` log file |

#### 2.3.7 Summary Display Removal from Business Logic

The following `_print_*_summary()` methods shall be removed from their respective business logic classes. Each caller shall receive the result object (per 2.1) and render the summary itself using the format appropriate to its interface.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.3.7 | | [x] | `TaggerManager._print_update_summary()` shall be removed. The CLI shall render the tag update summary from the returned `TagUpdateResult`. Format: 60-char-wide box with sections: header ("TAG UPDATE SUMMARY"), run metadata (date, directory, duration), FILES (processed/updated/skipped/errors), TAG UPDATES (title/album/artist/total), ORIGINAL TAG PROTECTION (stored counts), status line (checkmark or X emoji) |
| 2.3.8 | | [x] | `TaggerManager._print_restore_summary()` shall be removed. The CLI shall render the tag restore summary from the returned `TagRestoreResult`. Format: 60-char-wide box with sections: header ("TAG RESTORATION SUMMARY"), run metadata, FILES (processed/restored/skipped/errors), TAG RESTORATIONS (title/artist/album/total), status line |
| 2.3.9 | | [x] | `Converter._print_summary()` shall be removed. The CLI shall render the conversion summary from the returned `ConversionResult`. Format: 60-char-wide box with sections: header ("CONVERSION SUMMARY"), run metadata (date, input dir, output dir, duration, workers if >1), QUALITY SETTINGS (preset, mode description), FILES (found/converted/overwritten/skipped/errors), TAGGING (source tags copied), status line (checkmark, warning, or info emoji) |
| 2.3.10 | | [x] | `USBManager._print_usb_summary()` shall be removed. The CLI shall render the USB sync summary from the returned `USBSyncResult`. Format: 60-char-wide box with sections: header ("USB SYNC SUMMARY"), run metadata (date, source, destination, duration), FILES (found/copied/skipped/failed), status line |
| 2.3.11 | | [x] | `SummaryManager._print_summary()`, `_print_quick_summary()`, and `_print_detailed_summary()` shall be removed. The CLI shall render from the returned `LibrarySummaryResult`. Default format: 60-char-wide double-border box with sections: header ("PLAYLIST SUMMARY"), metadata (directory, scan date, duration), AGGREGATE STATISTICS (playlists/files/size/avg), TAG INTEGRITY (protection percentage, status), COVER ART (counts, percentages, status), PLAYLIST BREAKDOWN (table of playlists), final status. Quick format: header + directory + playlists/files/size/duration only. Detailed format: default + per-playlist extended breakdowns |
| 2.3.12 | | [x] | `PipelineOrchestrator._print_pipeline_summary()` shall be removed. The CLI shall render from the returned `PipelineResult`. Format: 70-char-wide box with sections: header ("PIPELINE SUMMARY"), run metadata (date, playlist name/key, duration), per-stage sections (DOWNLOAD/CONVERSION/TAGGING/USB SYNC with stats and status emoji), COMPREHENSIVE FILES SUMMARY (cross-stage totals), overall status line with failed stages list |
| 2.3.13 | | [x] | `PipelineOrchestrator.print_aggregate_summary()` shall be removed. The CLI shall render from the returned `AggregateResult`. Format: 70-char-wide box with sections: header ("TOTAL SUMMARY - ALL PLAYLISTS"), overview (playlists processed, duration, overall status), PLAYLIST RESULTS (table: Playlist / Downloaded / Converted / Tagged / Status), TOTALS row, CUMULATIVE STATISTICS (downloads/conversions/tags breakdowns), STATUS with failed playlist list |
| 2.3.14 | | [x] | `DependencyChecker` display methods (`display_summary()`, `_show_package_install_help()`, `_show_ffmpeg_install_help()`, `_show_venv_help()`) shall be removed from the class. Dependency status shall be returned as a `DependencyCheckResult` containing: `venv_active: bool`, `venv_path: str | None`, `packages: dict[str, bool]`, `ffmpeg_available: bool`, `all_ok: bool`, `missing_packages: list[str]`. The CLI renders install help messages |
| 2.3.15 | | [x] | `CoverArtManager` inline print blocks in `embed()`, `extract()`, `update()`, `strip()` shall be removed. Each method returns a `CoverArtResult` (per 2.1.13). The CLI renders the cover art operation summary |

### 2.4 Interface Contracts

Three interface layers shall implement the `UserPromptHandler` and render results from the service layer. Each interface is responsible for its own I/O and presentation. The business logic classes are shared unchanged across all three.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.4.1 | | [x] | **CLI interface** shall implement `UserPromptHandler` using standard `input()` calls with `[Y/n]` / `[y/N]` formatting. It shall render all result objects as formatted console boxes (60 or 70 char wide) matching the current visual output exactly. It shall use `tqdm` for progress bars and ANSI colors for status levels |
| 2.4.2 | | [x] | **Interactive CLI interface** (`InteractiveMenu` class) shall implement `UserPromptHandler` for its menu-driven workflow. It shall render results using the same console box formats as the CLI. The menu loop, playlist selection, action dispatch, and post-operation pauses remain in `InteractiveMenu` — these are interface concerns, not business logic |
| 2.4.3 | | [x] | **Web interface** shall implement `UserPromptHandler` by translating prompts to HTTP request/response cycles or WebSocket messages. Confirmation prompts become modal dialogs. Selection prompts become dropdown/radio UI. Text input prompts become form fields. Progress becomes server-sent events or WebSocket messages. Summaries become JSON responses rendered by the frontend |
| 2.4.4 | | [x] | The `InteractiveMenu` class shall remain as a CLI-specific interface component. It shall not contain business logic — only menu display, user input collection, and delegation to service layer methods. All business operations invoked by the menu shall go through the same service layer methods used by the CLI and Web interfaces |
| 2.4.5 | | [x] | The CLI argument parser (`argparse` setup in `main()`) shall remain a CLI-specific concern. The Web interface has its own routing and request parsing. Neither interface's request parsing shall live inside business logic classes |
| 2.4.6 | | [x] | All three interfaces shall import and use the same business logic classes with the same method signatures. Interface-specific behavior is controlled by which `UserPromptHandler` and `DisplayHandler` implementations are injected, not by flags or conditionals inside the business logic |
| 2.4.7 | | [x] | A `CLIPromptHandler` class shall implement `UserPromptHandler` using `input()` with formatted prompts. `confirm()` formats as `"message [Y/n] "` or `"message [y/N] "` based on default. `confirm_destructive()` formats as `"Type 'yes' to continue, anything else to cancel: "`. `select_from_list()` prints numbered options and reads an integer. `get_text_input()` prints prompt and reads a line. `wait_for_continue()` prints message and calls `input()` |
| 2.4.8 | | [x] | A `CLIDisplayHandler` class shall implement `DisplayHandler` using `print()` to stdout. `show_progress()` updates a `tqdm` progress bar or prints a line. `show_status()` prints with optional ANSI color based on level. `show_banner()` prints the startup banner |
| 2.4.9 | | [x] | A `CLISummaryRenderer` module (or set of functions) shall contain all summary formatting logic extracted from the removed `_print_*_summary()` methods. Each function takes a result object and prints the formatted console box. Functions: `render_tag_update_summary(result)`, `render_tag_restore_summary(result)`, `render_conversion_summary(result)`, `render_usb_sync_summary(result)`, `render_library_summary(result, mode)`, `render_pipeline_summary(result)`, `render_aggregate_summary(result)`, `render_dependency_check(result)`, `render_cover_art_summary(result)` |
| 2.4.10 | | [x] | The Web interface shall return result objects as JSON. Each result dataclass shall support serialization to a dict via a `to_dict()` method or Python's `dataclasses.asdict()`. The Web frontend renders summaries from the JSON data |

### 2.5 Logger Behavior

The `Logger` class bridges both file logging and optional console echo. Its behavior must be clearly defined in the separated architecture.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.5.1 | | [x] | `Logger` shall always write to the timestamped log file regardless of interface type (CLI, Interactive, Web) |
| 2.5.2 | | [x] | `Logger` shall accept an optional `echo_to_console: bool` parameter (default `True` for CLI, `False` for Web). When `True`, log messages are also printed to stdout. When `False`, log messages only go to the file |
| 2.5.3 | | [x] | `Logger` shall remain independent of `DisplayHandler`. Logger handles structured log messages; `DisplayHandler` handles user-facing display. A single operation may both log (to file) and display (to user) — these are separate concerns |
| 2.5.4 | | [x] | Business logic classes shall use `Logger` for operational logging (e.g., "Processing file X", "Error reading tags") and `DisplayHandler` for user-facing status (e.g., progress bars, summary headers). The distinction: Logger records what happened; DisplayHandler shows the user what's happening |

### 2.6 ProgressBar Integration

The existing `ProgressBar` class (tqdm wrapper) is a CLI-specific concern that must be abstracted.

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.6.1 | | [x] | The `ProgressBar` class shall remain as a CLI-specific implementation, not used directly by business logic classes |
| 2.6.2 | | [x] | Business logic classes that currently create `ProgressBar` instances directly shall instead call `display_handler.show_progress(current, total, message)` at each iteration |
| 2.6.3 | | [x] | The `CLIDisplayHandler` shall internally manage `ProgressBar` / tqdm instances, creating them on first `show_progress()` call for a given operation and closing them when the operation completes |
| 2.6.4 | | [x] | The Web `DisplayHandler` shall translate `show_progress()` calls into server-sent events or WebSocket messages containing `{current, total, message}` |

### 2.7 Edge Cases

| ID | Version | Tested | Requirement |
|----|---------|--------|-------------|
| 2.7.1 | | [x] | **Error propagation:** When a business logic method encounters an error, it shall set `success=False` on the result object and populate an `errors` count. It shall NOT raise exceptions for expected failure modes (file not found, conversion error, permission denied). Unexpected exceptions shall propagate naturally to the caller |
| 2.7.2 | | [x] | **Timeout handling:** The `UserPromptHandler.wait_for_continue()` method shall accept an optional `timeout: float | None` parameter (seconds). If the timeout expires, the method returns as if the user acknowledged. Default: `None` (no timeout). Web interface should always set a reasonable timeout (e.g., 300 seconds) to prevent hung requests |
| 2.7.3 | | [x] | **Cancellation:** Business logic operations that iterate over files shall check an optional `cancelled: threading.Event` flag between iterations. If set, the operation shall stop early, set `success=False`, and return partial results in the result object. This enables the Web interface to support cancel buttons |
| 2.7.4 | | [x] | **Concurrent operations:** Business logic classes shall be stateless between method calls (statistics are reset at the start of each operation). This allows the Web interface to handle concurrent requests by creating separate instances per request. The `Logger` class shall be thread-safe for concurrent log writes |
| 2.7.5 | | [x] | **Non-interactive fallback:** When `UserPromptHandler` is `None` and a business logic method needs user input, it shall use the `NonInteractivePromptHandler` defaults (per 2.2.7). This ensures operations never block waiting for input that cannot arrive (e.g., Web API with no WebSocket) |
| 2.7.6 | | [x] | **Partial results on interruption:** If a batch operation (e.g., converting 50 files) is interrupted by error or cancellation after processing some files, the result object shall reflect the partial progress (e.g., `converted=23, errors=1, total_found=50`) rather than reporting zero |
| 2.7.7 | | [x] | **Handler hot-swap prevention:** Once a business logic class is constructed with a `UserPromptHandler` and `DisplayHandler`, those handlers shall not be changed during an operation. Handlers are set at construction time and remain fixed for the lifetime of that instance |
| 2.7.8 | | [x] | **Backward compatibility during migration:** While interfaces are being migrated incrementally, a `LegacyDisplayHandler` shall be available that reproduces the current `print()`-based behavior exactly, allowing classes to be migrated one at a time without changing visible output |
