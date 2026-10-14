"""Field-level encryption for sensitive identifiers.

AES-256-GCM with a random nonce per value. A keyed HMAC "blind index" lets us look an
identifier up by equality without storing it in the clear. Ciphertexts carry a version
prefix so keys can be rotated later without a flag day.
"""

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_VERSION = "v1"


class FieldCrypto:
    def __init__(self, master_key_b64: str) -> None:
        master = base64.b64decode(master_key_b64)
        if len(master) != 32:
            raise ValueError("Field encryption key must decode to exactly 32 bytes")
        # Independent subkeys: compromise of the index key must not expose the cipher key.
        self._enc = HKDF(hashes.SHA256(), 32, None, b"aarogya-field-enc").derive(master)
        self._idx = HKDF(hashes.SHA256(), 32, None, b"aarogya-blind-index").derive(master)

    def encrypt(self, plaintext: str, *, context: str) -> str:
        nonce = os.urandom(12)
        ct = AESGCM(self._enc).encrypt(nonce, plaintext.encode(), context.encode())
        return f"{_VERSION}:{base64.urlsafe_b64encode(nonce + ct).decode()}"

    def decrypt(self, token: str, *, context: str) -> str:
        version, _, body = token.partition(":")
        if version != _VERSION:
            raise ValueError("Unknown ciphertext version")
        raw = base64.urlsafe_b64decode(body)
        return AESGCM(self._enc).decrypt(raw[:12], raw[12:], context.encode()).decode()

    def encrypt_bytes(self, data: bytes, *, context: str) -> bytes:
        """Binary AES-256-GCM (used for audio chunks): nonce || ciphertext+tag."""
        nonce = os.urandom(12)
        return nonce + AESGCM(self._enc).encrypt(nonce, data, context.encode())

    def decrypt_bytes(self, blob: bytes, *, context: str) -> bytes:
        return AESGCM(self._enc).decrypt(blob[:12], blob[12:], context.encode())

    def blind_index(self, value: str, *, context: str) -> str:
        msg = f"{context}\x00{value}".encode()
        return hmac.new(self._idx, msg, hashlib.sha256).hexdigest()
