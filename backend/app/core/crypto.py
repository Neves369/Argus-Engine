from __future__ import annotations

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _get_fernet() -> Fernet | None:
    key = get_settings().encryption_key
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        return None


def encrypt_secret(plaintext: str) -> str | None:
    """Cifra um segredo (string) usando Fernet. Retorna o ciphertext em base64."""
    fernet = _get_fernet()
    if fernet is None:
        return None
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str | None:
    """De-cifra um segredo (string) usando Fernet. Retorna o plaintext."""
    fernet = _get_fernet()
    if fernet is None:
        return None
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        return None


def has_encryption() -> bool:
    """Retorna True se a chave de criptografia estiver configurada."""
    return _get_fernet() is not None