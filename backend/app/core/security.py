from __future__ import annotations

import threading

from app.core.config import get_settings

_kill_switch = threading.Event()


class ScopeValidationError(ValueError):
    """Raised when a target is outside the authorized scope."""


def is_kill_switch_active() -> bool:
    return _kill_switch.is_set() or get_settings().kill_switch


def activate_kill_switch() -> None:
    _kill_switch.set()


def deactivate_kill_switch() -> None:
    _kill_switch.clear()


def is_devil_mode_enabled(devil_mode: bool) -> bool:
    """Resolve whether execution mode is actually active.

    The execution path only activates when the run requests it, the operator
    enabled it globally, and the kill-switch is not engaged. Sandbox (Docker)
    and HITL are enforced in later stages.
    """
    if not devil_mode:
        return False
    if not get_settings().devil_mode:
        return False
    if is_kill_switch_active():
        return False
    return True


def validate_scope(target: str) -> str:
    """Validate that a target falls within the authorized scope.

    Returns the normalized target on success, raises ScopeValidationError otherwise.
    """
    settings = get_settings()
    allowed = [s.strip().lower() for s in settings.allowed_scopes if s.strip()]
    target_clean = (target or "").strip().lower()

    if not target_clean:
        raise ScopeValidationError("Target is empty.")

    if allowed and not any(
        target_clean == scope or target_clean.endswith("." + scope) for scope in allowed
    ):
        raise ScopeValidationError(f"Target '{target}' is not in the authorized scope.")

    return target_clean
