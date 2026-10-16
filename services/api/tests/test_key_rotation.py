import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.crypto import FieldCrypto
from app.core.db import set_tenant
from app.modules.patients.rotation import rotate_identifiers
from tests.helpers import make_patient, reception

OLD = base64.b64encode(b"o" * 32).decode()
NEW = base64.b64encode(b"n" * 32).decode()
H = dict[str, str]


def test_rotation_keeps_old_values_readable_and_writes_with_the_new_key() -> None:
    old = FieldCrypto(OLD)
    token = old.encrypt("1234-5678", context="abha")
    assert token.startswith(f"v2.{old.key_id}:")
    both = FieldCrypto(NEW, [OLD])
    assert both.decrypt(token, context="abha") == "1234-5678"
    assert both.needs_rotation(token)
    fresh = both.encrypt("1234-5678", context="abha")
    assert fresh.startswith(f"v2.{both.key_id}:") and not both.needs_rotation(fresh)
    # Only the new key: the old value is refused, plainly, not garbled.
    with pytest.raises(ValueError, match="not configured"):
        FieldCrypto(NEW).decrypt(token, context="abha")
    # The wrong context still fails.
    with pytest.raises(ValueError):
        both.decrypt(fresh, context="other")
    assert both.blind_indexes("x", context="c")[0] == both.blind_index("x", context="c")
    assert both.blind_indexes("x", context="c")[1] == old.blind_index("x", context="c")
    with pytest.raises(ValueError, match="twice"):
        FieldCrypto(OLD, [OLD])


def test_values_written_before_key_ids_existed_still_decrypt() -> None:
    import os

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    enc = HKDF(hashes.SHA256(), 32, None, b"aarogya-field-enc").derive(base64.b64decode(OLD))
    nonce = os.urandom(12)
    ct = AESGCM(enc).encrypt(nonce, b"legacy", b"ctx")
    v1 = "v1:" + base64.urlsafe_b64encode(nonce + ct).decode()
    assert FieldCrypto(NEW, [OLD]).decrypt(v1, context="ctx") == "legacy"


def test_audio_chunks_written_with_an_older_key_still_decrypt() -> None:
    blob = FieldCrypto(OLD).encrypt_bytes(b"pcm", context="k")
    assert FieldCrypto(NEW, [OLD]).decrypt_bytes(blob, context="k") == b"pcm"
    with pytest.raises(ValueError):
        FieldCrypto(NEW).decrypt_bytes(blob, context="k")


def test_rotating_stored_identifiers_keeps_lookups_working(
    client: TestClient, org_a: H, db: Session
) -> None:
    recep = reception(client, org_a, "alpha-clinic")
    ident = {"system": "EXTERNAL_MRN", "value": "HOSP-778899"}
    p = make_patient(client, recep, "Ravi Kumar", identifiers=[ident])
    assert p["id"]
    rotated = FieldCrypto(NEW, [client.app.state.settings.field_encryption_key])  # type: ignore[attr-defined]

    set_tenant(db, None, bypass=True)
    before = db.execute(text("select value_ciphertext, value_index from patient_identifiers")).one()
    assert rotate_identifiers(db, rotated) == 1
    set_tenant(db, None, bypass=True)
    after = db.execute(text("select value_ciphertext, value_index from patient_identifiers")).one()
    assert after[0] != before[0] and after[1] != before[1]
    assert rotated.decrypt(after[0], context="patient-identifier:EXTERNAL_MRN") == ident["value"]
    assert rotate_identifiers(db, rotated) == 0  # nothing left; safe to run again

    # A server that now runs on the new key (older one listed) sees the same person as a duplicate.
    client.app.state.crypto = rotated  # type: ignore[attr-defined]
    r = client.post(
        "/api/v1/patients",
        headers=recep,
        json={
            "full_name": "Someone Entirely Different",
            "age_years": 30,
            "administrative_gender": "female",
            "identifiers": [ident],
        },
    )
    assert r.status_code == 409, r.text
