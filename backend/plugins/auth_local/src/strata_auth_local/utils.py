"""Password hashing utilities using Argon2id via pwdlib."""

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

_hasher: PasswordHash = PasswordHash((Argon2Hasher(),))


def hash_password(plain: str) -> str:
    """Return an Argon2id hash of *plain*.

    Args:
        plain: The raw password string.

    Returns:
        An Argon2id hash string suitable for storage.
    """
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches the Argon2id *hashed* value.

    Args:
        plain: The raw password string to verify.
        hashed: The stored Argon2id hash.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    return _hasher.verify(plain, hashed)
