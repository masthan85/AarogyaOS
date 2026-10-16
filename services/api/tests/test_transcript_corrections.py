"""Correcting what the recogniser heard, without losing what it heard."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.ai_helpers import DOCTOR, PATIENT, ai_interaction, ai_visit, analyse, say
from tests.clinical_helpers import Visit, get
from tests.conftest import make_staff

H = dict[str, str]


def put(client: TestClient, h: H, url: str, body: dict[str, Any]) -> Any:
    return client.put(f"/api/v1{url}", headers=h, json=body)


def fixture(client: TestClient, org_a: H, db: Session) -> tuple[Visit, str, list[str]]:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    ids = say(
        db, iid, [(DOCTOR, "What brings you in?"), (PATIENT, "I have had fewer for three days.")]
    )
    return v, iid, ids


def segments(client: TestClient, h: H, iid: str) -> list[dict[str, Any]]:
    return list(get(client, h, f"/interactions/{iid}/transcript").json()["segments"])


def test_a_correction_is_shown_beside_the_original_which_never_changes(
    client: TestClient, org_a: H, db: Session
) -> None:
    v, iid, ids = fixture(client, org_a, db)
    url = f"/interactions/{iid}/segments/{ids[1]}/correction"
    r = put(client, v.doctor, url, {"text": "I have had fever for three days."})
    assert r.status_code == 200, r.text
    assert r.json()["corrected_text"] == "I have had fever for three days."
    seg = segments(client, v.doctor, iid)[1]
    assert seg["raw_text"] == "I have had fewer for three days."
    assert seg["corrected_text"] == "I have had fever for three days."
    assert segments(client, v.doctor, iid)[0]["corrected_text"] is None
    # The newest correction wins; null puts it back to what was heard.
    put(client, v.doctor, url, {"text": "I have had fever for four days."})
    assert segments(client, v.doctor, iid)[1]["corrected_text"] == "I have had fever for four days."
    put(client, v.doctor, url, {"text": None})
    assert segments(client, v.doctor, iid)[1]["corrected_text"] is None


def test_who_may_correct_and_what_is_refused(client: TestClient, org_a: H, db: Session) -> None:
    v, iid, ids = fixture(client, org_a, db)
    url = f"/interactions/{iid}/segments/{ids[1]}/correction"
    assert put(client, v.recep, url, {"text": "x"}).status_code == 403
    assert put(client, v.admin, url, {"text": "x"}).status_code == 403
    # A nurse holds the permission but cannot see a recording a doctor made.
    assert put(client, v.nurse, url, {"text": "Fever for three days."}).status_code == 404
    assert put(client, v.doctor, url, {"text": "   "}).status_code == 422
    assert put(client, v.doctor, url, {"text": "x" * 2001}).status_code == 422
    other = f"/interactions/{iid}/segments/{ids[1].replace(ids[1][:8], '00000000')}/correction"
    assert put(client, v.doctor, other, {"text": "x"}).status_code == 404
    stranger, _ = make_staff(client, org_a, "dr.other@x.example.com", "doctor", "alpha-clinic")
    assert put(client, stranger, url, {"text": "x"}).status_code in (403, 404)


def test_corrections_are_audited_without_their_text_and_cannot_be_edited_with_sql(
    client: TestClient, org_a: H, db: Session
) -> None:
    v, iid, ids = fixture(client, org_a, db)
    put(
        client,
        v.doctor,
        f"/interactions/{iid}/segments/{ids[1]}/correction",
        {"text": "Secret fever"},
    )
    log = get(client, v.admin, "/audit-logs", action="TRANSCRIPT_CORRECTED").json()
    assert len(log) == 1 and "Secret" not in str(log)
    from app.core.db import set_tenant

    set_tenant(db, None, bypass=True)
    for sql in (
        "update transcript_corrections set text = 'x'",
        "delete from transcript_corrections",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(sql))
        db.rollback()
        set_tenant(db, None, bypass=True)


def test_the_assistant_reads_the_corrected_text_and_quotes_it(
    client: TestClient, org_a: H, db: Session
) -> None:
    v, iid, ids = fixture(client, org_a, db)
    # Nothing has been analysed yet, so the correction is in place before the assistant reads.
    fix = "I have had fever for three days."
    put(client, v.doctor, f"/interactions/{iid}/segments/{ids[1]}/correction", {"text": fix})
    assert analyse(client, v.doctor, iid).json()["status"] == "OK"
    found = get(client, v.doctor, f"/interactions/{iid}/ai/candidates").json()
    fever = [c for c in found if c["text"] == "fever"]
    assert fever and fever[0]["evidence"][0]["quote"] in fix
