"""Retained audio in S3-compatible storage, against an in-memory S3 (moto). The store only ever sees
encrypted frames, recordings survive a pause and a failed upload, and key rotation works there too."""

import base64
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import FieldCrypto
from app.modules.interactions.retention import purge_due_audio
from app.speech.audio_store import S3EncryptedAudioStore, audio_store_from_settings
from tests.speech_helpers import recording_ready, start_session, stream, token_of
from tests.test_gateway import audio_rows, authed, closes_with, connect

OLD = base64.b64encode(b"o" * 32).decode()
NEW = base64.b64encode(b"n" * 32).decode()
BUCKET = "clinic-audio"
H = dict[str, str]


@pytest.fixture
def s3() -> Iterator[Any]:
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
        )
        yield client


def store(
    s3: Any, tmp_path: Path, crypto: FieldCrypto | None = None, **kw: Any
) -> S3EncryptedAudioStore:
    return S3EncryptedAudioStore(
        s3, BUCKET, crypto or FieldCrypto(OLD), str(tmp_path / "spool"), prefix="audio/", **kw
    )


def objects(s3: Any) -> list[str]:
    return [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])]


def test_audio_is_uploaded_encrypted_and_reads_back(s3: Any, tmp_path: Path) -> None:
    st = store(s3, tmp_path, server_side_encryption="AES256")
    w = st.writer("org/one.audio")
    w.append(b"SECRET-PCM" * 50)
    w.append(b"second")
    assert w.close() == 506
    assert objects(s3) == ["audio/org/one.audio"]
    raw = s3.get_object(Bucket=BUCKET, Key="audio/org/one.audio")
    assert b"SECRET-PCM" not in raw["Body"].read()
    assert raw["ServerSideEncryption"] == "AES256"
    assert list(st.read_chunks("org/one.audio")) == [b"SECRET-PCM" * 50, b"second"]
    assert list((tmp_path / "spool").iterdir()) == []  # nothing is left on local disk
    assert st.exists("org/one.audio") and not st.exists("org/other.audio")
    assert st.delete("org/one.audio") and objects(s3) == []
    assert st.delete("org/one.audio") is False


def test_a_resumed_recording_continues_the_same_object(s3: Any, tmp_path: Path) -> None:
    st = store(s3, tmp_path)
    first = st.writer("org/r.audio")
    first.append(b"before the pause")
    first.close()
    second = st.writer("org/r.audio")
    second.append(b"after it")
    second.close()
    assert list(st.read_chunks("org/r.audio")) == [b"before the pause", b"after it"]


def test_a_failed_upload_is_kept_readable_and_retried(s3: Any, tmp_path: Path) -> None:
    st = store(s3, tmp_path)
    real = s3.upload_file

    def broken(*_: Any, **__: Any) -> None:
        raise ConnectionError("network down")

    s3.upload_file = broken
    w = st.writer("org/f.audio")
    w.append(b"kept safe")
    w.close()  # does not raise: the connection's clean-up must still run
    assert objects(s3) == []
    assert st.exists("org/f.audio")
    assert list(st.read_chunks("org/f.audio")) == [b"kept safe"]
    s3.upload_file = real
    assert st.upload_pending() == 1
    assert objects(s3) == ["audio/org/f.audio"]
    assert list((tmp_path / "spool").iterdir()) == []
    assert list(st.read_chunks("org/f.audio")) == [b"kept safe"]


def test_rotation_re_encrypts_the_object(s3: Any, tmp_path: Path) -> None:
    w = store(s3, tmp_path).writer("org/k.audio")
    w.append(b"pcm")
    w.close()
    rotating = store(s3, tmp_path, FieldCrypto(NEW, [OLD]))
    assert rotating.rewrap("org/k.audio") is True
    assert rotating.rewrap("org/k.audio") is False
    assert list(store(s3, tmp_path, FieldCrypto(NEW)).read_chunks("org/k.audio")) == [b"pcm"]


def test_storage_keys_cannot_escape_the_prefix(s3: Any, tmp_path: Path) -> None:
    st = store(s3, tmp_path)
    for bad in ("../x", "/abs", "a//b", "a/./b", ""):
        with pytest.raises(ValueError):
            st.writer(bad)


def test_settings_choose_the_store_and_refuse_half_configurations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="BUCKET"):
        Settings(audio_store="s3")
    with pytest.raises(ValueError, match="KMS"):
        Settings(audio_store="s3", audio_s3_bucket="b", audio_s3_kms_key_id="k")
    local = Settings(audio_store_path=str(tmp_path))
    assert type(audio_store_from_settings(local, FieldCrypto(OLD))).__name__ == (
        "LocalEncryptedAudioStore"
    )
    with mock_aws():
        s3_settings = Settings(
            audio_store="s3",
            audio_s3_bucket=BUCKET,
            audio_s3_region="ap-south-1",
            audio_store_path=str(tmp_path),
        )
        assert isinstance(
            audio_store_from_settings(s3_settings, FieldCrypto(OLD)), S3EncryptedAudioStore
        )


def test_a_retained_recording_goes_to_s3_and_is_purged_there(
    client: TestClient, org_a: H, db: Session, s3: Any, tmp_path: Path
) -> None:
    app_store = S3EncryptedAudioStore(
        s3,
        BUCKET,
        client.app.state.crypto,
        str(tmp_path / "spool"),
        prefix="audio/",  # type: ignore[attr-defined]
    )
    client.app.state.audio_store = app_store  # type: ignore[attr-defined]
    v = recording_ready(client, org_a, retain_days=7)
    session = start_session(client, v)
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 2)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    key = audio_rows(db)[0][0]
    assert objects(s3) == [f"audio/{key}"]
    assert b"".join(app_store.read_chunks(key))  # readable with the clinic's key
    assert purge_due_audio(db, app_store, datetime.now(UTC) + timedelta(days=8)) == 1
    assert objects(s3) == []
