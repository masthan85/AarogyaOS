"""Re-encrypt stored identifiers under the current field key (see app/core/crypto.py)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import FieldCrypto
from app.core.db import set_tenant
from app.modules.patients.models import PatientIdentifier
from app.modules.patients.service import _ident_context


def rotate_identifiers(session: Session, crypto: FieldCrypto, *, batch: int = 200) -> int:
    """Re-encrypts every identifier not yet under the current key and returns how many it did.

    Stops with an error if a value needs a key that is not configured. Safe to run again."""
    set_tenant(session, None, bypass=True)
    done = 0
    while True:
        rows = session.scalars(
            select(PatientIdentifier)
            .where(~PatientIdentifier.value_ciphertext.startswith(f"v2.{crypto.key_id}:"))
            .order_by(PatientIdentifier.id)
            .limit(batch)
        ).all()
        if not rows:
            break
        for row in rows:
            context = _ident_context(row.system)
            value = crypto.decrypt(row.value_ciphertext, context=context)
            row.value_ciphertext = crypto.encrypt(value, context=context)
            row.value_index = crypto.blind_index(value, context=context)
            done += 1
        session.commit()
        set_tenant(session, None, bypass=True)
    return done
