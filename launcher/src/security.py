"""
security.py — Mimir Security Primitives

PIN hashing (bcrypt), AES-256-GCM log encryption, and PBKDF2 key derivation.
No UI code here — pure logic only.

Key derivation: PBKDF2-HMAC-SHA256 with 600k iterations, 32-byte output.
Log encryption: AES-256-GCM with random 12-byte nonce per write.
Encrypted log format: {"_mimir_enc_v1": "<base64(nonce + ciphertext + GCM tag)>"}
"""

import os
import base64
import json

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

_ENC_MARKER = "_mimir_enc_v1"
_PBKDF2_ITERATIONS = 600_000
_BCRYPT_ROUNDS = 12


# ── PIN hashing ──────────────────────────────────────────────────────────────

def hash_pin(pin: str) -> str:
    """Hash a PIN with bcrypt (cost 12). Returns the hash as a str."""
    hashed = bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return hashed.decode("utf-8")


def verify_pin(pin: str, hashed: str) -> bool:
    """Verify a PIN against a stored bcrypt hash."""
    if not pin or not hashed:
        return False
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── Key derivation ───────────────────────────────────────────────────────────

def new_salt() -> str:
    """Generate a fresh 16-byte random salt, base64-encoded."""
    return base64.b64encode(os.urandom(16)).decode("utf-8")


def derive_key(pin: str, salt_b64: str) -> bytes:
    """
    Derive a 32-byte AES-256 key from a PIN using PBKDF2-HMAC-SHA256.
    salt_b64: base64-encoded 16-byte salt stored in mimir.json.
    """
    salt = base64.b64decode(salt_b64)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(pin.encode("utf-8"))


# ── Log encryption ───────────────────────────────────────────────────────────

def encrypt_log(plaintext: str, key: bytes) -> str:
    """
    Encrypt a log JSON string with AES-256-GCM.
    Returns a single-line JSON string: {"_mimir_enc_v1": "<base64>"}
    The base64 payload encodes: 12-byte nonce || ciphertext+tag
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = base64.b64encode(nonce + ciphertext).decode("utf-8")
    return json.dumps({_ENC_MARKER: payload})


def decrypt_log(content: str, key: bytes) -> str:
    """
    Decrypt a Mimir-encrypted log file.
    - If content is plain JSON (no marker), returns it unchanged.
    - On authentication failure, raises ValueError.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, Exception):
        return content

    if _ENC_MARKER not in data:
        return content  # Plain (unencrypted) log — pass through

    try:
        raw = base64.b64decode(data[_ENC_MARKER])
        nonce, ciphertext = raw[:12], raw[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Log decryption failed: {exc}") from exc


def is_encrypted_log(content: str) -> bool:
    """Return True if this content is a Mimir-encrypted log."""
    try:
        return _ENC_MARKER in json.loads(content)
    except Exception:
        return False
