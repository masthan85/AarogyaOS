import base64
from datetime import date

import pytest

from app.core.config import Settings
from app.core.crypto import FieldCrypto
from app.modules.patients.normalise import (
    age_years,
    dob_from_age,
    mask_mobile,
    normalise_abha_number,
    normalise_mobile,
    normalise_name,
)

KEY = base64.b64encode(b"k" * 32).decode()


def test_encrypt_roundtrip_and_randomised() -> None:
    c = FieldCrypto(KEY)
    a, b = c.encrypt("91-1234-5678-9012", context="x"), c.encrypt("91-1234-5678-9012", context="x")
    assert a != b and "9012" not in a
    assert c.decrypt(a, context="x") == "91-1234-5678-9012"


def test_ciphertext_is_bound_to_its_context_and_key() -> None:
    c = FieldCrypto(KEY)
    token = c.encrypt("secret", context="ABHA_NUMBER")
    with pytest.raises(Exception):  # noqa: B017, PT011
        c.decrypt(token, context="OTHER")
    other = FieldCrypto(base64.b64encode(b"z" * 32).decode())
    with pytest.raises(Exception):  # noqa: B017, PT011
        other.decrypt(token, context="ABHA_NUMBER")


def test_blind_index_is_deterministic_keyed_and_context_separated() -> None:
    c = FieldCrypto(KEY)
    assert c.blind_index("v", context="a") == c.blind_index("v", context="a")
    assert c.blind_index("v", context="a") != c.blind_index("v", context="b")
    assert c.blind_index("v", context="a") != FieldCrypto(
        base64.b64encode(b"z" * 32).decode()
    ).blind_index("v", context="a")


def test_key_must_be_32_bytes() -> None:
    with pytest.raises(ValueError):
        FieldCrypto(base64.b64encode(b"short").decode())


def test_production_requires_real_field_key() -> None:
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret="x" * 40)
    Settings(
        environment="production",
        jwt_secret="x" * 40,
        field_encryption_key=KEY,
        database_url="postgresql+psycopg://aarogya_app:not-the-dev-password@db/aarogya",
    )


@pytest.mark.parametrize(
    "raw", ["9876543210", "+91 98765 43210", "09876543210", "0091-98765-43210", "91 9876543210"]
)
def test_mobile_variants_normalise_to_e164(raw: str) -> None:
    assert normalise_mobile(raw) == "+919876543210"


@pytest.mark.parametrize("raw", ["12345", "5876543210", "98765432100", "abcdefghij", ""])
def test_invalid_mobiles_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        normalise_mobile(raw)


def test_mask_mobile() -> None:
    assert mask_mobile("+919876543210") == "+91 XXXXXX3210"
    assert mask_mobile(None) is None


def test_names_normalise_titles_punctuation_and_common_variants() -> None:
    assert normalise_name("Dr. Mohd. Rafi") == normalise_name("Muhammad  RAFI") == "mohammed rafi"
    assert normalise_name("Smt. Lakshmi Devi") == "lakshmi devi"


def test_abha_number_format() -> None:
    assert normalise_abha_number("91123456789012") == "91-1234-5678-9012"
    with pytest.raises(ValueError):
        normalise_abha_number("1234")


def test_age_helpers() -> None:
    assert age_years(date(2000, 6, 15), date(2026, 6, 14)) == 25
    assert age_years(date(2000, 6, 15), date(2026, 6, 15)) == 26
    assert age_years(None, date(2026, 1, 1)) is None
    assert dob_from_age(40, date(2026, 10, 13)) == date(1986, 1, 1)
