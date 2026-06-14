"""
Fernet symmetric encryption wrapper for all OAuth token storage.

Usage:
    from app.core.encryption import encrypt_token, decrypt_token

    encrypted = encrypt_token(raw_access_token)   # store this in DB
    raw = decrypt_token(encrypted)                 # retrieve for API calls

Key management:
    - ENCRYPTION_KEY must be set in environment (base64url Fernet key)
    - Generate once: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    - NEVER regenerate the key for an existing database — all existing tokens become unreadable
    - Back up the key separately from the database
"""

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """
    Initialize Fernet cipher once per process lifetime.
    Cached so we don't reconstruct on every token operation.
    Raises ValueError at startup if ENCRYPTION_KEY is missing or malformed.
    """
    key = settings.ENCRYPTION_KEY
    if not key:
        raise ValueError(
            "ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise ValueError(f"ENCRYPTION_KEY is invalid — must be a valid Fernet key: {e}") from e


def encrypt_token(plaintext: str) -> str:
    """
    Encrypt a plaintext OAuth token string.
    Returns a base64url-encoded ciphertext string safe to store in DB.
    """
    if not plaintext:
        raise ValueError("Cannot encrypt empty token")
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a Fernet-encrypted token string.
    Raises InvalidToken if ciphertext is tampered or key has changed.
    Never logs the plaintext.
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt empty ciphertext")
    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        logger.error(
            "Token decryption failed — ciphertext tampered or ENCRYPTION_KEY changed. "
            "This is a critical error: users will need to reconnect their accounts."
        )
        raise InvalidToken("Token decryption failed") from e


def rotate_encrypted_token(old_ciphertext: str, new_plaintext: str) -> str:
    """
    Convenience: decrypt an old token (verify it's valid) then encrypt a new one.
    Used when refreshing OAuth tokens — ensures old token was valid before writing new one.
    """
    # Verify old token is decryptable (guards against silent corruption)
    decrypt_token(old_ciphertext)
    return encrypt_token(new_plaintext)