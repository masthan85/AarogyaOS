"""Where retained audio lives. Only used when policy AND consent allow retention.

Development adapter: encrypted files on local disk. Production uses encrypted S3-compatible
object storage (Phase 7); it implements the same small interface.
"""

import os
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from app.core.crypto import FieldCrypto


class AudioWriter(Protocol):
    def append(self, chunk: bytes) -> None: ...
    def close(self) -> int: ...


class AudioStore(Protocol):
    def writer(self, key: str) -> AudioWriter: ...
    def read_chunks(self, key: str) -> Iterator[bytes]: ...
    def delete(self, key: str) -> bool: ...
    def exists(self, key: str) -> bool: ...
    def rewrap(self, key: str) -> bool:
        """Re-encrypt under the current key. False if it already was. Never while being written."""
        ...


class _LocalWriter:
    def __init__(self, path: Path, crypto: FieldCrypto, key: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("ab")
        self._crypto, self._key = crypto, key
        self.size = 0

    def append(self, chunk: bytes) -> None:
        blob = self._crypto.encrypt_bytes(chunk, context=self._key)
        self._fh.write(struct.pack(">I", len(blob)) + blob)
        self.size += len(chunk)

    def close(self) -> int:
        self._fh.close()
        return self.size


class LocalEncryptedAudioStore:
    def __init__(self, root: str, crypto: FieldCrypto) -> None:
        self._root = Path(root)
        self._crypto = crypto

    def _frames(self, key: str) -> Iterator[bytes]:
        with self._path(key).open("rb") as fh:
            while header := fh.read(4):
                (length,) = struct.unpack(">I", header)
                yield fh.read(length)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root.resolve() not in path.parents:
            raise ValueError("Invalid storage key")  # no path traversal
        return path

    def writer(self, key: str) -> AudioWriter:
        return _LocalWriter(self._path(key), self._crypto, key)

    def read_chunks(self, key: str) -> Iterator[bytes]:
        for blob in self._frames(key):
            yield self._crypto.decrypt_bytes(blob, context=key)

    def rewrap(self, key: str) -> bool:
        if not any(self._crypto.bytes_need_rotation(b, context=key) for b in self._frames(key)):
            return False
        path = self._path(key)
        tmp = path.with_name(path.name + ".rewrap")
        # Written beside the original and swapped in whole, so a crash leaves one complete copy.
        with tmp.open("wb") as fh:
            for chunk in self.read_chunks(key):
                blob = self._crypto.encrypt_bytes(chunk, context=key)
                fh.write(struct.pack(">I", len(blob)) + blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return True

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._path(key).exists()
