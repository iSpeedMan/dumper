"""
crypto.py — AES-256-GCM encryption/decryption for device credentials.

All device passwords/enable secrets are stored encrypted in the database.
The master key is loaded from config.yaml and never stored in the DB.

Format of encrypted blob: base64( nonce[12] + ciphertext + tag[16] )
"""

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.config import settings


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _derive_key(master_key_str: str) -> bytes:
    """
    Derive a 32-byte AES key from the master key string using PBKDF2-HMAC-SHA256.
    A fixed application salt is used (no per-record salt needed since the key
    itself is secret). If you change the master key, all encrypted data becomes
    unreadable — back it up.
    """
    # Fixed application salt — not a secret, just ensures domain separation
    SALT = b"dumper-app-salt-v1"

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=200_000,
    )
    return kdf.derive(master_key_str.encode("utf-8"))


# Cache the derived key for the process lifetime (avoid repeated KDF calls)
_KEY_CACHE: Optional[bytes] = None


def _get_key() -> bytes:
    global _KEY_CACHE
    if _KEY_CACHE is None:
        master = settings.encryption.master_key
        if not master or master.startswith("CHANGE_ME"):
            raise RuntimeError(
                "Encryption master key is not configured. "
                "Set 'encryption.master_key' in config.yaml."
            )
        _KEY_CACHE = _derive_key(master)
    return _KEY_CACHE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encrypt(plaintext: str) -> str:
    """
    Encrypt a plaintext string using AES-256-GCM.
    Returns a base64-encoded string safe to store in SQLite TEXT column.

    Raises RuntimeError if the master key is not configured.
    """
    if not plaintext:
        return ""

    key = _get_key()
    aesgcm = AESGCM(key)

    # 12-byte random nonce (96-bit) — standard for GCM
    nonce = os.urandom(12)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    # Pack: nonce + ciphertext+tag, then base64-encode for safe DB storage
    blob = nonce + ciphertext_with_tag
    return base64.b64encode(blob).decode("ascii")


def decrypt(encrypted_b64: str) -> str:
    """
    Decrypt a base64-encoded AES-256-GCM blob back to plaintext.

    Raises ValueError on authentication failure (tampered/corrupted data).
    Raises RuntimeError if the master key is not configured.
    """
    if not encrypted_b64:
        return ""

    key = _get_key()
    aesgcm = AESGCM(key)

    try:
        blob = base64.b64decode(encrypted_b64.encode("ascii"))
        nonce = blob[:12]
        ciphertext_with_tag = blob[12:]
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
        return plaintext_bytes.decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Decryption failed (key mismatch or corrupted data): {exc}") from exc


def rotate_key(old_master_key: str, new_master_key: str, encrypted_value: str) -> str:
    """
    Re-encrypt a value under a new master key.
    Use this when rotating the master key in bulk across all DB records.
    """
    # Temporarily override the cache to decrypt with old key
    global _KEY_CACHE
    old_cache = _KEY_CACHE

    _KEY_CACHE = _derive_key(old_master_key)
    plaintext = decrypt(encrypted_value)

    _KEY_CACHE = _derive_key(new_master_key)
    new_encrypted = encrypt(plaintext)

    # Restore original cache
    _KEY_CACHE = old_cache
    return new_encrypted
