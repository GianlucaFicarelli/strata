"""Stateless download tokens.

Download tokens authorise a specific user to download from a specific storage
backend for a short window of time.  They are embedded in the ``?token=``
query parameter of ``GET /api/files/download`` so that plain ``<a href>``
links work without JavaScript or cookie support.

Design
------
A token is an HMAC-SHA256 signature over a canonical payload string::

    "{user_id}:{backend_id}:{exp}"

where ``exp`` is a Unix timestamp (integer seconds UTC).  The raw bytes are
URL-safe base64 encoded (no padding) and prepended with the payload, giving::

    "{user_id}:{backend_id}:{exp}.{base64_signature}"

The full token is opaque from the client's perspective: it can be decoded but
not forged without ``STRATA_ENCRYPTION_KEY``.

The key material is derived from ``STRATA_ENCRYPTION_KEY`` — the same key
used for AES-256-GCM field encryption — via HKDF-SHA256.  This avoids
introducing a separate secret while keeping the two uses cryptographically
independent.

Revocation
----------
None.  Tokens are single-use by convention only; the short TTL (default 5
minutes) is the primary control.  A Redis round-trip is deliberately avoided
to keep downloads stateless.
"""

import base64
import hashlib
import hmac
import logging
import time

from fastapi import HTTPException, status

from strata.config import settings

L = logging.getLogger(__name__)

# Domain-separation label for HKDF
_HKDF_INFO = b"strata-download-token-v1"


def _signing_key() -> bytes:
    """Derive a 32-byte signing key from ``STRATA_ENCRYPTION_KEY`` via HKDF.

    Using HKDF means the download-token signing key is cryptographically
    independent from the AES-GCM encryption key, even though both derive from
    the same secret.

    Returns:
        32-byte HMAC-SHA256 signing key.

    Raises:
        RuntimeError: If ``STRATA_ENCRYPTION_KEY`` is empty.
    """
    if not settings.ENCRYPTION_KEY:
        raise RuntimeError(
            "STRATA_ENCRYPTION_KEY must be set to issue download tokens."
        )
    # Simple single-step HKDF-Expand (RFC 5869 §2.3, L=32, no salt needed
    # because the input key is already high-entropy base64).
    ikm = settings.ENCRYPTION_KEY.encode()
    prk = hmac.new(b"\x00" * 32, ikm, hashlib.sha256).digest()
    okm = hmac.new(prk, _HKDF_INFO + b"\x01", hashlib.sha256).digest()
    return okm


def _sign(payload: str) -> str:
    """Return the URL-safe base64 HMAC-SHA256 signature of *payload*.

    Args:
        payload: The canonical string to sign.

    Returns:
        URL-safe base64 string (no padding).
    """
    key = _signing_key()
    digest = hmac.new(key, payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def issue_download_token(user_id: str, backend_id: str) -> str:
    """Issue a short-lived download token for *user_id* and *backend_id*.

    The token is valid for ``STRATA_DOWNLOAD_TOKEN_TTL_SECONDS`` (default
    5 minutes).  It embeds the expiry so verification requires no storage
    lookup.

    Args:
        user_id: ``core_users.id`` of the requesting user.
        backend_id: ``core_storage_instances.id`` UUID of the target backend.

    Returns:
        Opaque URL-safe token string suitable for use as ``?token=``.
    """
    exp = int(time.time()) + settings.DOWNLOAD_TOKEN_TTL_SECONDS
    payload = f"{user_id}:{backend_id}:{exp}"
    sig = _sign(payload)
    return f"{payload}.{sig}"


def verify_download_token(token: str) -> tuple[str, str]:
    """Verify a download token and return ``(user_id, backend_id)``.

    Raises HTTP 401 if the token is missing, malformed, expired, or has an
    invalid signature.  No storage lookup is performed.

    Args:
        token: The raw value of the ``?token=`` query parameter.

    Returns:
        A ``(user_id, backend_id)`` tuple extracted from the verified token.

    Raises:
        HTTPException: 401 on any verification failure.
    """
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired download token",
    )

    if not token:
        raise _invalid

    try:
        payload, sig = token.rsplit(".", 1)
    except ValueError:
        raise _invalid

    # Constant-time signature comparison
    expected_sig = _sign(payload)
    if not hmac.compare_digest(sig, expected_sig):
        L.warning("Download token signature mismatch")
        raise _invalid

    try:
        user_id, backend_id, exp_str = payload.split(":")
        exp = int(exp_str)
    except ValueError:
        raise _invalid

    if int(time.time()) > exp:
        raise _invalid

    return user_id, backend_id
