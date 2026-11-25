"""Where retained audio lives. Only used when policy AND consent allow retention.

Two adapters share one small interface and one file format: a sequence of frames, each a 4-byte
big-endian length followed by one chunk encrypted with the field key (AES-256-GCM, the storage key
bound in as authenticated data). The store never sees audio in the clear.

`LocalEncryptedAudioStore` keeps files on local disk (development, or one container with a volume).
`S3EncryptedAudioStore` keeps objects in S3-compatible storage. Objects cannot be appended to, so a
recording is spooled to local disk as it arrives and uploaded whole when its connection closes; a
resumed recording downloads its object first and is uploaded again on close. An upload that fails
leaves the spool file in place, and `upload_pending` (run by the audio purge job) retries it.
"""

import hashlib
import logging
import os
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any, Protocol

from app.core.crypto import FieldCrypto

log = logging.getLogger("aarogya.audio")


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


def _frames_of(fh: IO[bytes]) -> Iterator[bytes]:
    while header := fh.read(4):
        (length,) = struct.unpack(">I", header)
        blob = fh.read(length)
        if len(blob) != length:
            raise ValueError("Audio file is truncated")
        yield blob


def _frame(blob: bytes) -> bytes:
    return struct.pack(">I", len(blob)) + blob


def _check_key(key: str) -> str:
    parts = key.split("/")
    if not key or key.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Invalid storage key")
    return key


class _LocalWriter:
    def __init__(self, path: Path, crypto: FieldCrypto, key: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("ab")
        self._crypto, self._key = crypto, key
        self.size = 0

    def append(self, chunk: bytes) -> None:
        blob = self._crypto.encrypt_bytes(chunk, context=self._key)
        self._fh.write(_frame(blob))
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
            yield from _frames_of(fh)

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
                fh.write(_frame(blob))
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


class _S3Writer:
    def __init__(self, store: "S3EncryptedAudioStore", key: str, spool: Path) -> None:
        self._store, self._key, self._spool = store, key, spool
        self._fh = spool.open("ab")
        self.size = 0

    def append(self, chunk: bytes) -> None:
        self._fh.write(_frame(self._store._crypto.encrypt_bytes(chunk, context=self._key)))
        self.size += len(chunk)

    def close(self) -> int:
        self._fh.close()
        self._store._upload(self._key, self._spool)
        return self.size


class S3EncryptedAudioStore:
    def __init__(
        self,
        client: Any,
        bucket: str,
        crypto: FieldCrypto,
        spool_dir: str,
        *,
        prefix: str = "",
        server_side_encryption: str = "",
        kms_key_id: str = "",
    ) -> None:
        self._s3, self._bucket, self._crypto = client, bucket, crypto
        self._prefix = prefix
        self._spool_dir = Path(spool_dir)
        self._spool_dir.mkdir(parents=True, exist_ok=True)
        # Encryption by the storage service is in addition to ours, never instead of it.
        self._extra: dict[str, str] = {}
        if server_side_encryption:
            self._extra["ServerSideEncryption"] = server_side_encryption
        if kms_key_id:
            self._extra["SSEKMSKeyId"] = kms_key_id

    def _object(self, key: str) -> str:
        return self._prefix + _check_key(key)

    def _spool(self, key: str) -> Path:
        # Named by a hash, with the key alongside, so no storage key can become a local path.
        name = hashlib.sha256(_check_key(key).encode()).hexdigest()
        return self._spool_dir / f"{name}.part"

    def _remote_exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self._bucket, Key=self._object(key))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def _upload(self, key: str, spool: Path) -> bool:
        try:
            self._s3.upload_file(
                str(spool), self._bucket, self._object(key), ExtraArgs=dict(self._extra) or None
            )
        except Exception as exc:  # noqa: BLE001  (kept on disk and retried by upload_pending)
            log.error("audio upload failed; kept for retry", extra={"error": type(exc).__name__})
            return False
        spool.unlink(missing_ok=True)
        spool.with_suffix(".key").unlink(missing_ok=True)
        return True

    def writer(self, key: str) -> AudioWriter:
        spool = self._spool(key)
        if not spool.exists() and self._remote_exists(key):
            # A resumed recording: continue from what was uploaded when it paused.
            self._s3.download_file(self._bucket, self._object(key), str(spool))
        spool.with_suffix(".key").write_text(key)  # lets upload_pending find a failed upload
        return _S3Writer(self, key, spool)

    def _open(self, key: str) -> IO[bytes]:
        spool = self._spool(key)
        if spool.exists():
            return spool.open("rb")
        body: IO[bytes] = self._s3.get_object(Bucket=self._bucket, Key=self._object(key))["Body"]
        return body

    def read_chunks(self, key: str) -> Iterator[bytes]:
        fh = self._open(key)
        try:
            for blob in _frames_of(fh):
                yield self._crypto.decrypt_bytes(blob, context=key)
        finally:
            fh.close()

    def delete(self, key: str) -> bool:
        found = self.exists(key)
        spool = self._spool(key)
        spool.unlink(missing_ok=True)
        spool.with_suffix(".key").unlink(missing_ok=True)
        self._s3.delete_object(Bucket=self._bucket, Key=self._object(key))
        return found

    def exists(self, key: str) -> bool:
        return self._spool(key).exists() or self._remote_exists(key)

    def rewrap(self, key: str) -> bool:
        fh = self._open(key)
        try:
            blobs = list(_frames_of(fh))
        finally:
            fh.close()
        if not any(self._crypto.bytes_need_rotation(b, context=key) for b in blobs):
            return False
        spool = self._spool(key)
        tmp = spool.with_suffix(".rewrap")
        with tmp.open("wb") as out:
            for blob in blobs:
                chunk = self._crypto.decrypt_bytes(blob, context=key)
                out.write(_frame(self._crypto.encrypt_bytes(chunk, context=key)))
        os.replace(tmp, spool)
        spool.with_suffix(".key").write_text(key)
        if not self._upload(key, spool):
            raise RuntimeError("Re-encrypted audio could not be uploaded; it is kept for retry")
        return True

    def upload_pending(self) -> int:
        """Upload recordings whose upload failed earlier. Returns how many went up."""
        done = 0
        for spool in self._spool_dir.glob("*.part"):
            marker = spool.with_suffix(".key")
            if marker.exists() and self._upload(marker.read_text(), spool):
                done += 1
        return done


def audio_store_from_settings(settings: Any, crypto: FieldCrypto) -> AudioStore:
    if settings.audio_store != "s3":
        return LocalEncryptedAudioStore(settings.audio_store_path, crypto)
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=settings.audio_s3_endpoint_url or None,
        region_name=settings.audio_s3_region or None,
    )  # credentials come from the standard AWS chain (environment, role), never from settings
    return S3EncryptedAudioStore(
        client,
        settings.audio_s3_bucket,
        crypto,
        settings.audio_store_path,
        prefix=settings.audio_s3_prefix,
        server_side_encryption=settings.audio_s3_server_side_encryption,
        kms_key_id=settings.audio_s3_kms_key_id,
    )
