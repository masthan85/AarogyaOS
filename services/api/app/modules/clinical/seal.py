"""A tamper-evident seal on signed prescriptions.

This is NOT a legal digital signature (no certificate, no Aadhaar eSign): it is a keyed hash taken
at the moment the doctor signs, over who signed, when, and every line of the prescription. If anyone
changes the stored prescription afterwards, including someone with direct database access who
cannot read the server's key, the seal no longer matches and the check says so.
"""

import hashlib
import hmac
import json
from datetime import UTC
from typing import Any

from app.core.config import get_settings


def _keys() -> list[bytes]:
    """Signing key first: dedicated seal keys (if set), then keys derived from the field key."""
    s = get_settings()
    raw = [s.field_encryption_key, *[k for k in s.field_encryption_previous_keys.split(",") if k]]
    derived = [hashlib.sha256(f"aarogya-seal-v1:{k}".encode()).digest() for k in raw]
    dedicated = [
        hashlib.sha256(f"aarogya-seal-key:{k.strip()}".encode()).digest()
        for k in s.seal_keys.split(",")
        if k.strip()
    ]
    return [*dedicated, *derived]


_ITEM_FIELDS = (
    "position", "medicine_name", "generic_name", "brand_name", "strength", "form", "dose",
    "route", "frequency", "duration_days", "quantity", "instructions", "medication_code",
    "code_system",
)  # fmt: skip


def canonical(rx: Any, items: list[Any]) -> bytes:
    body = {
        "id": str(rx.id),
        "patient_id": str(rx.patient_id),
        "encounter_id": str(rx.encounter_id),
        "practitioner_id": str(rx.practitioner_id),
        "signed_by": str(rx.signed_by),
        "signed_at": rx.signed_at.astimezone(UTC).isoformat(),
        "notes": rx.notes,
        "items": [{f: getattr(i, f) for f in _ITEM_FIELDS} for i in items],
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def compute(rx: Any, items: list[Any]) -> str:
    return hmac.new(_keys()[0], canonical(rx, items), hashlib.sha256).hexdigest()


def matches(rx: Any, items: list[Any]) -> bool:
    data = canonical(rx, items)
    return any(
        hmac.compare_digest(hmac.new(k, data, hashlib.sha256).hexdigest(), rx.seal or "")
        for k in _keys()
    )
