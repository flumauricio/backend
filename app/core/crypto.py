"""
app/core/crypto.py
──────────────────
Symmetric encryption for BotEnvVar secrets using Fernet (AES-128-CBC + HMAC-SHA256).

Public API
──────────
  encrypt_secret(value)     → encrypted ciphertext string (Fernet token, URL-safe base64)
  decrypt_secret(value)     → plaintext string — handles both encrypted AND legacy plaintext
  mask_secret(value)        → "••••••••" always; None-safe

Compatibility guarantee
───────────────────────
Existing rows may hold plaintext values written before this module was
introduced.  decrypt_secret detects the difference:

  • Fernet tokens always start with "gAAA" (base64-encoded version byte 0x80).
  • Any value that cannot be decoded as a valid Fernet token is assumed to
    be legacy plaintext and returned as-is.

This means old rows continue to work without a migration — they are silently
treated as plaintext.  New writes always encrypt.

Key hygiene
───────────
  • The key is read from settings once at import time and kept in a module-
    level Fernet instance (_fernet).
  • The raw key bytes are never logged or exposed.
  • We intentionally do NOT store the key in any variable other than the
    Fernet instance, so it can't be accidentally serialised.

Rotation (future)
─────────────────
  To rotate keys, wrap _fernet in a cryptography.fernet.MultiFernet with
  [new_fernet, old_fernet].  MultiFernet.rotate() can re-encrypt all rows
  in a background job.
"""

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_logger = logging.getLogger(__name__)

# ─── Fernet prefix that all valid tokens share ────────────────────────────────
# Fernet tokens are base64url-encoded.  The first decoded byte is always
# 0x80 (version), which encodes to "gA" in standard base64.  In URL-safe
# base64 (no padding issues for the first byte) the token always begins
# with "gAAA" — reliable enough as a heuristic for legacy detection.
_FERNET_TOKEN_PREFIX = b"gAAA"

# ─── Module-level Fernet instance (single key, lazy-validated) ───────────────

def _build_fernet() -> Fernet:
    """
    Instantiate Fernet from settings.SECRET_ENCRYPTION_KEY.

    The key must be a URL-safe base64-encoded 32-byte value, exactly as
    produced by Fernet.generate_key().  Settings validates/generates it.
    """
    raw: str = settings.SECRET_ENCRYPTION_KEY  # already validated by Settings
    try:
        return Fernet(raw.encode())
    except Exception as exc:  # ValueError from bad key format
        # This is a fatal misconfiguration — crash early rather than silently
        # falling back and storing plaintext in "production secret" fields.
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY is set but is not a valid Fernet key. "
            "Generate a correct key with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


_fernet: Fernet = _build_fernet()

# ─── Public helpers ───────────────────────────────────────────────────────────

_MASK = "••••••••"


def encrypt_secret(value: str) -> str:
    """
    Encrypt *value* with Fernet and return the token as a plain str.

    The returned string is URL-safe base64 (no binary characters) and is
    safe to store in a TEXT / VARCHAR database column.

    Never logs the plaintext value.
    """
    token: bytes = _fernet.encrypt(value.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(value: str) -> str:
    """
    Decrypt a Fernet-encrypted *value* and return the plaintext str.

    Backwards-compatible: if *value* does not look like a Fernet token
    (i.e. it was written by an older version of the code before encryption
    was introduced), the original string is returned unchanged.

    Never logs the decrypted value.
    """
    if not value:
        return value

    # Fast heuristic: Fernet tokens always begin with "gAAA" in ASCII.
    # This avoids an expensive base64 decode + Fernet parse for every
    # legacy plaintext value.
    if not value.encode("ascii", errors="replace").startswith(_FERNET_TOKEN_PREFIX):
        # Definitely not a Fernet token — legacy plaintext.
        return value

    # Attempt full Fernet decryption.
    try:
        plaintext: bytes = _fernet.decrypt(value.encode("ascii"))
        return plaintext.decode("utf-8")
    except InvalidToken:
        # Starts with "gAAA" but is not a valid token for our key —
        # could be a value that coincidentally starts with those bytes,
        # or encrypted with a different key.  Treat as legacy plaintext
        # to avoid bricking existing rows.
        _logger.warning(
            "decrypt_secret: value looks like a Fernet token but failed to decrypt; "
            "treating as legacy plaintext. "
            "If this is unexpected, verify SECRET_ENCRYPTION_KEY has not changed."
        )
        return value
    except Exception as exc:
        # Any other decryption error — log without the value, return as-is.
        _logger.error(
            "decrypt_secret: unexpected error during decryption, returning as-is",
            error=type(exc).__name__,
        )
        return value


def mask_secret(value: str | None) -> str:
    """
    Return the fixed mask string regardless of whether *value* is
    encrypted, plaintext, or None.

    This is the only function that should be called when building API
    responses — it intentionally discards the actual value.
    """
    if value is None:
        return _MASK
    return _MASK


def is_encrypted(value: str) -> bool:
    """
    Return True if *value* appears to be a Fernet-encrypted token.

    Useful for migration scripts and admin tooling.  Not used in the
    hot path — prefer always calling encrypt_secret() on write.
    """
    if not value:
        return False
    if not value.encode("ascii", errors="replace").startswith(_FERNET_TOKEN_PREFIX):
        return False
    try:
        _fernet.decrypt(value.encode("ascii"))
        return True
    except Exception:
        return False
