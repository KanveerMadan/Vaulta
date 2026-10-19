"""
Field-level envelope encryption.

Each user has a random 256-bit data key. It is stored only wrapped: AES-256-GCM under a key derived from MASTER_KEY
(an environment variable, never in the database), with the user id as associated data. Columns typed `Encrypted` /
`EncryptedJSON` hold AES-256-GCM ciphertext under that data key, also bound to the user id:

    e1:<base64url(nonce ‖ ciphertext ‖ tag)>     random 96-bit nonce: equal values encrypt differently
    s1:<base64url(nonce ‖ ciphertext ‖ tag)>     `Searchable`: the nonce is an HMAC-SHA256 blind index of the value
                                                  (BLIND_INDEX_KEY, user id), so within one user equal values encrypt
                                                  equally and SQL can GROUP BY, compare and enforce UNIQUE on them

Which user's key is in use comes from app.core.scope (bound per request by get_current_user, and per unit of work in
internal jobs). With no user bound, reading or writing an encrypted column raises: nothing falls back to plaintext.
Values without a prefix are returned as they are, so a database that is partway through the encryption migration
(alembic f6a2c8e0b1d3) keeps working; tests/test_encryption.py asserts that no plaintext is left after it.

Wrapped data keys:  k1:<key id>:<base64url(nonce ‖ wrapped key ‖ tag)>, key id = first 8 hex chars of
SHA-256(KEK). MASTER_KEY_PREVIOUS is accepted for unwrapping while scripts/rotate_master_key.py re-wraps every key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from functools import lru_cache
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

MIN_KEY_LENGTH = 32
RANDOM, SEARCHABLE, WRAPPED = "e1:", "s1:", "k1:"


class CryptoError(Exception):
    """A key is missing or wrong, or a value was tampered with."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _derive(secret: str, info: bytes) -> bytes:
    if len(secret) < MIN_KEY_LENGTH:
        raise CryptoError(f"key material must be at least {MIN_KEY_LENGTH} characters")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(secret.encode())


# ── Master key (wraps data keys) ──────────────────────────────────────────────

class _Kek:
    def __init__(self, secret: str):
        self.key = _derive(secret, b"vaulta kek v1")
        self.id = hashlib.sha256(self.key).hexdigest()[:8]
        self.aead = AESGCM(self.key)


@lru_cache(maxsize=4)
def _kek(secret: str) -> _Kek:
    return _Kek(secret)


def current_kek() -> _Kek:
    if not settings.MASTER_KEY:
        raise CryptoError("MASTER_KEY is not set")
    return _kek(settings.MASTER_KEY)


def _keks() -> dict[str, _Kek]:
    keks = [current_kek()] + ([_kek(settings.MASTER_KEY_PREVIOUS)] if settings.MASTER_KEY_PREVIOUS else [])
    return {k.id: k for k in keks}


def new_data_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def wrap(data_key: bytes, user_id: uuid.UUID, kek: Optional[_Kek] = None) -> str:
    kek = kek or current_kek()
    nonce = os.urandom(12)
    return f"{WRAPPED}{kek.id}:{_b64(nonce + kek.aead.encrypt(nonce, data_key, user_id.bytes))}"


def unwrap(wrapped: str, user_id: uuid.UUID, keks: Optional[dict] = None) -> bytes:
    try:
        prefix, kek_id, body = wrapped.split(":", 2)
        kek = (keks or _keks())[kek_id]
        raw = _unb64(body)
        return kek.aead.decrypt(raw[:12], raw[12:], user_id.bytes)
    except KeyError:
        raise CryptoError("data key is wrapped by an unknown master key (is MASTER_KEY_PREVIOUS needed?)") from None
    except Exception as e:
        raise CryptoError(f"data key can't be unwrapped: {e.__class__.__name__}") from None


def wrapped_by_current(wrapped: str) -> bool:
    return wrapped.startswith(f"{WRAPPED}{current_kek().id}:")


# ── Blind index ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=2)
def _index_key(secret: str) -> bytes:
    return _derive(secret, b"vaulta blind index v1")


def blind_index(user_id: uuid.UUID, value: str) -> bytes:
    """HMAC-SHA256(BLIND_INDEX_KEY, user id ‖ value). Different users get different indexes for the same value."""
    if not settings.BLIND_INDEX_KEY:
        raise CryptoError("BLIND_INDEX_KEY is not set")
    return hmac.new(_index_key(settings.BLIND_INDEX_KEY), user_id.bytes + value.encode(), hashlib.sha256).digest()


def lookup_hash(purpose: str, value: str) -> str:
    """Keyed hash for finding a row before any user is known (forwarding addresses): HMAC, so a dump can't be
    brute-forced back to the address."""
    if not settings.BLIND_INDEX_KEY:
        raise CryptoError("BLIND_INDEX_KEY is not set")
    return hmac.new(_index_key(settings.BLIND_INDEX_KEY), f"{purpose}|{value}".encode(), hashlib.sha256).hexdigest()


# ── Per-user cipher ───────────────────────────────────────────────────────────

class UserCipher:
    def __init__(self, user_id: uuid.UUID, data_key: bytes):
        self.user_id = user_id
        self._aead = AESGCM(data_key)
        self._aad = user_id.bytes

    def encrypt(self, plaintext: str, searchable: bool = False) -> str:
        data = plaintext.encode()
        nonce = blind_index(self.user_id, plaintext)[:12] if searchable else os.urandom(12)
        return (SEARCHABLE if searchable else RANDOM) + _b64(nonce + self._aead.encrypt(nonce, data, self._aad))

    def decrypt(self, value: str) -> str:
        try:
            raw = _unb64(value[3:])
            return self._aead.decrypt(raw[:12], raw[12:], self._aad).decode()
        except Exception:
            raise CryptoError("value can't be decrypted with this user's key") from None


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value[:3] in (RANDOM, SEARCHABLE)


# ── Column types ──────────────────────────────────────────────────────────────

def _cipher() -> UserCipher:
    from app.core.scope import current_cipher
    return current_cipher()


class Encrypted(TypeDecorator):
    """Text encrypted with the bound user's data key (random nonce)."""
    impl = Text
    cache_ok = True
    searchable = False

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _cipher().encrypt(self._dump(value), self.searchable)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self._load(_cipher().decrypt(value) if is_encrypted(value) else value)

    def _dump(self, value) -> str:
        return str(value)

    def _load(self, text: str):
        return text


class Searchable(Encrypted):
    """Deterministic per user (blind-index nonce): supports =, IN, GROUP BY and UNIQUE in SQL, not LIKE or ordering."""
    cache_ok = True
    searchable = True


class EncryptedJSON(Encrypted):
    """JSON document encrypted as a whole. Not queryable in SQL."""
    cache_ok = True

    def _dump(self, value) -> str:
        return json.dumps(value, separators=(",", ":"), default=str)

    def _load(self, text):
        return json.loads(text) if isinstance(text, str) else text
