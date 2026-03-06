"""
core.protocols - Abstract protocol interfaces (UserPromptHandler, DisplayHandler).

No internal dependencies.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

# ══════════════════════════════════════════════════════════════════
# Section 5b: Service Layer — Protocols, Results, Handlers, Renderers
# ══════════════════════════════════════════════════════════════════

# ── Protocols ─────────────────────────────────────────────────────

@runtime_checkable
class UserPromptHandler(Protocol):
    """Protocol for user interaction callbacks.

    Business logic classes accept an optional UserPromptHandler at
    construction. When no handler is provided, NonInteractivePromptHandler
    is used as a fail-safe default.
    """

    def confirm(self, message: str, default: bool = True) -> bool: ...

    def confirm_destructive(self, message: str) -> bool: ...

    def select_from_list(self, prompt: str, options: list[str],
                         allow_cancel: bool = True) -> int | None: ...

    def get_text_input(self, prompt: str,
                       default: str | None = None) -> str | None: ...

    def wait_for_continue(self, message: str,
                          timeout: float | None = None) -> None: ...


@runtime_checkable
class DisplayHandler(Protocol):
    """Protocol for progress and status display.

    Business logic classes accept an optional DisplayHandler at
    construction. When no handler is provided, NullDisplayHandler
    is used (silently discards all calls).
    """

    def show_progress(self, current: int, total: int,
                      message: str) -> None: ...

    def finish_progress(self) -> None: ...

    def show_status(self, message: str,
                    level: str = "info") -> None: ...

    def show_banner(self, title: str,
                    subtitle: str | None = None) -> None: ...


# ── Handler Implementations ───────────────────────────────────────

