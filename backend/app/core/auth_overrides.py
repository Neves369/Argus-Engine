from __future__ import annotations

_ui_password_override: str | None = None


def set_ui_password_override(value: str) -> None:
    """Define a senha efetiva em memória (carregada do banco no lifespan)."""
    global _ui_password_override
    _ui_password_override = value


def clear_ui_password_override() -> None:
    global _ui_password_override
    _ui_password_override = None


def has_ui_password_override() -> bool:
    """True quando a senha atual vem do override persistido (não do env)."""
    return bool(_ui_password_override)


def effective_ui_password() -> str:
    """Senha do operador efetiva: override persistido no banco (rotacionado)
    tem prioridade sobre `UI_PASSWORD` do ambiente. Vazia = modo aberto (dev)."""
    if _ui_password_override:
        return _ui_password_override
    from app.core.config import get_settings

    return get_settings().ui_password