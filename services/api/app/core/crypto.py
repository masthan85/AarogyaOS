"""Field-level encryption for sensitive identifiers.

AES-256-GCM with a random nonce per value. A keyed HMAC "blind index" lets us look an
identifier up by equality without storing it in the clear.

Key rotation: the first key is the current one and is used for everything written. Older keys
can be listed after it so existing data stays readable while it is re-encrypted (see
`rotate-field-key` in app/cli.py). Ciphertexts name the key that wrote them (`v2.<key id>:`);
older `v1:` values did not, so they are tried against each key in turn. Blind indexes depend on
the key, so lookups check the index under every listed key until rotation has finished.
"""

import base64
import hashlib
import hmac
import os
from collections.abc import Sequence

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings


class _Key:
    def __init__(self, master_key_b64: str) -> None:
        master = base64.b64decode(master_key_b64)
        if len(master) != 32:
            raise ValueError("Field encryption key must decode to exactly 32 bytes")
        # Independent subkeys: compromise of the index key must not expose the cipher key.
        self.enc = HKDF(hashes.SHA256(), 32, None, b"aarogya-field-enc").derive(master)
        self.idx = HKDF(hashes.SHA256(), 32, None, b"aarogya-blind-index").derive(master)
        # A short public label, derived one way, so a value can say which key wrote it.
        self.kid = hashlib.sha256(b"aarogya-key-id" + master).hexdigest()[:8]


class FieldCrypto:
    def __init__(self, master_key_b64: str, previous_keys_b64: Sequence[str] = ()) -> None:
        self._keys = [_Key(master_key_b64), *(_Key(k) for k in previous_keys_b64)]
        if len({k.kid for k in self._keys}) != len(self._keys):
            raise ValueError("The same field encryption key is listed twice")

    @property
    def key_id(self) -> str:
        return self._keys[0].kid

    def encrypt(self, plaintext: str, *, context: str) -> str:
        key = self._keys[0]
        nonce = os.urandom(12)
        ct = AESGCM(key.enc).encrypt(nonce, plaintext.encode(), context.encode())
        return f"v2.{key.kid}:{base64.urlsafe_b64encode(nonce + ct).decode()}"

    def decrypt(self, token: str, *, context: str) -> str:
        version, _, body = token.partition(":")
        if version == "v1":
            candidates = self._keys
        elif version.startswith("v2."):
            candidates = [k for k in self._keys if k.kid == version[3:]]
            if not candidates:
                raise ValueError("This value was encrypted with a key that is not configured")
        else:
            raise ValueError("Unknown ciphertext version")
        raw = base64.urlsafe_b64decode(body)
        for key in candidates:
            try:
                return AESGCM(key.enc).decrypt(raw[:12], raw[12:], context.encode()).decode()
            except InvalidTag:
                continue
        raise ValueError("Could not decrypt: wrong key or altered data")

    def needs_rotation(self, token: str) -> bool:
        return not token.startswith(f"v2.{self._keys[0].kid}:")

    def encrypt_bytes(self, data: bytes, *, context: str) -> bytes:
        """Binary AES-256-GCM (used for audio chunks): nonce || ciphertext+tag."""
        nonce = os.urandom(12)
        return nonce + AESGCM(self._keys[0].enc).encrypt(nonce, data, context.encode())

    def decrypt_bytes(self, blob: bytes, *, context: str) -> bytes:
        for key in self._keys:
            try:
                return AESGCM(key.enc).decrypt(blob[:12], blob[12:], context.encode())
            except InvalidTag:
                continue
        raise ValueError("Could not decrypt: wrong key or altered data")

    def blind_index(self, value: str, *, context: str) -> str:
        return self._index(self._keys[0], value, context)

    def blind_indexes(self, value: str, *, context: str) -> list[str]:
        """The index under every configured key: current first, then older ones."""
        return [self._index(k, value, context) for k in self._keys]

    @staticmethod
    def _index(key: _Key, value: str, context: str) -> str:
        msg = f"{context}\x00{value}".encode()
        return hmac.new(key.idx, msg, hashlib.sha256).hexdigest()


def crypto_from_settings(settings: Settings) -> FieldCrypto:
    previous = [k.strip() for k in settings.field_encryption_previous_keys.split(",") if k.strip()]
    return FieldCrypto(settings.field_encryption_key, previous)
