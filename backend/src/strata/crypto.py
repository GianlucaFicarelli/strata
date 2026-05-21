"""AES-256-GCM field-level encryption for secret config values.

Used by the storage instance API to encrypt/decrypt individual field values
that are marked ``secret=True`` in a StorageTemplate's config schema.

Key management
--------------
The key is read from ``STRATA_ENCRYPTION_KEY``, which must be a URL-safe
base64-encoded 32-byte value (Fernet-compatible format, but we use raw
AES-GCM here for explicit control over the ciphertext format).

Ciphertext format (all binary, concatenated):
    12 bytes  — random nonce (GCM standard)
    16 bytes  — GCM authentication tag (appended by encrypt())
    N  bytes  — ciphertext

The result is stored as base64 in the JSON config column.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _load_key(raw: str) -> bytes:
    """Decode the base64 key and validate its length."""
    try:
        key_bytes = base64.urlsafe_b64decode(raw + "==")
    except Exception as exc:
        raise ValueError("STRATA_ENCRYPTION_KEY is not valid base64") from exc
    if len(key_bytes) != 32:
        raise ValueError(
            f"STRATA_ENCRYPTION_KEY must decode to exactly 32 bytes, got {len(key_bytes)}"
        )
    return key_bytes


def encrypt_field(value: str, raw_key: str) -> str:
    """Encrypt a single string field value.

    Args:
        value: Plain-text string to encrypt.
        raw_key: URL-safe base64 key from ``STRATA_ENCRYPTION_KEY``.

    Returns:
        URL-safe base64-encoded ciphertext (nonce + tag + ciphertext).
    """
    key = _load_key(raw_key)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    # AESGCM.encrypt() returns ciphertext + tag (tag appended)
    ct_and_tag = aesgcm.encrypt(nonce, value.encode(), None)
    return base64.urlsafe_b64encode(nonce + ct_and_tag).decode()


def decrypt_field(token: str, raw_key: str) -> str:
    """Decrypt a single string field value.

    Args:
        token: URL-safe base64-encoded ciphertext produced by :func:`encrypt_field`.
        raw_key: URL-safe base64 key from ``STRATA_ENCRYPTION_KEY``.

    Returns:
        Decrypted plain-text string.

    Raises:
        ValueError: If decryption fails (wrong key, tampered ciphertext).
    """
    key = _load_key(raw_key)
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(token + "==")
    nonce, ct_and_tag = raw[:12], raw[12:]
    try:
        return aesgcm.decrypt(nonce, ct_and_tag, None).decode()
    except Exception as exc:
        raise ValueError("Decryption failed — wrong key or corrupted ciphertext") from exc
