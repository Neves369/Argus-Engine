from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_overrides import (
    clear_ui_password_override,
)
from app.core.auth_overrides import (
    set_ui_password_override as set_ui_password_override_in_memory,
)
from app.core.crypto import decrypt_secret, encrypt_secret, has_encryption
from app.db.models import AppSetting
from app.db.session import async_session_factory

UI_PASSWORD_KEY = "ui_password"


async def load_ui_password_override_from_db() -> None:
    """Carrega para a memória a senha rotacionada (se houver, cifrada no banco).

    Só roda no lifespan quando a criptografia está configurada — sem chave não
    há override persistido.
    """
    clear_ui_password_override()
    async with async_session_factory() as db:
        row = await db.get(AppSetting, UI_PASSWORD_KEY)
        if row is None or not row.value_encrypted:
            return
        plain = decrypt_secret(row.value_encrypted)
        if plain:
            set_ui_password_override_in_memory(plain)


async def set_ui_password_override(plain: str, db: AsyncSession) -> None:
    """Cifra e persiste a nova senha, aplicando-a já em memória."""
    if not has_encryption():
        raise RuntimeError("ARGUS_ENCRYPTION_KEY não configurada")
    set_ui_password_override_in_memory(plain)
    cipher = encrypt_secret(plain)
    await db.merge(
        AppSetting(key=UI_PASSWORD_KEY, value_encrypted=cipher)
    )
    await db.flush()
    await db.commit()