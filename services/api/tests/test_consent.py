from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import set_tenant
from app.modules.consent.models import PURPOSES
from tests.clinical_helpers import API, get, post
from tests.conftest import make_staff
from tests.helpers import make_patient, reception
from tests.speech_helpers import grant, install_wording

H = dict[str, str]
URL = "/patients/{}/consents"


@pytest.fixture
def ready(client: TestClient, org_a: H) -> dict[str, Any]:
    install_wording(client, org_a)
    recep = reception(client, org_a, "alpha-clinic")
    return {"admin": org_a, "recep": recep, "patient": make_patient(client, recep)}


def status(client: TestClient, h: H, pid: str) -> dict[str, dict[str, Any]]:
    body = get(client, h, URL.format(pid)).json()
    return {s["purpose"]: s for s in body["status"]}


def test_templates_cover_every_purpose_are_flagged_unreviewed_and_installed_once(
    client: TestClient, org_a: H
) -> None:
    first = post(client, org_a, "/consent-policies/install-templates")
    assert first.status_code == 201
    assert {p["purpose"] for p in first.json()} == set(PURPOSES)
    assert all(p["legally_reviewed"] is False and p["version"] == 1 for p in first.json())
    assert post(client, org_a, "/consent-policies/install-templates").json() == []


def test_new_wording_is_a_new_version_and_old_consents_keep_the_version_they_saw(
    client: TestClient, ready: dict[str, Any], org_a: H
) -> None:
    pid = ready["patient"]["id"]
    old = grant(client, ready["recep"], pid, "AUDIO_RECORDING")[0]
    assert old["policy_version"] == 1
    new = post(
        client,
        org_a,
        "/consent-policies",
        {
            "purpose": "AUDIO_RECORDING",
            "title": "Recording (reviewed)",
            "legally_reviewed": True,
            "body": "Reviewed wording that explains recording clearly to the patient.",
        },
    )
    assert new.json()["version"] == 2 and new.json()["legally_reviewed"] is True
    resp = get(client, org_a, "/consent-policies")
    assert resp.status_code == 200, resp.text
    active = {p["purpose"]: p for p in resp.json()}
    assert active["AUDIO_RECORDING"]["version"] == 2
    assert len(get(client, org_a, "/consent-policies", include_retired=True).json()) == 9
    assert status(client, ready["recep"], pid)["AUDIO_RECORDING"]["policy_version"] == 1


def test_only_administrators_publish_wording_but_clinical_staff_can_read_it(
    client: TestClient, ready: dict[str, Any], org_a: H
) -> None:
    body = {
        "purpose": "RESEARCH",
        "title": "Research",
        "body": "Some wording long enough to count.",
    }
    for h in (
        ready["recep"],
        make_staff(client, org_a, "dr@alpha-clinic.example.com", "doctor", "alpha-clinic")[0],
    ):
        assert post(client, h, "/consent-policies", body).status_code == 403
        assert get(client, h, "/consent-policies").status_code == 200
    assert (
        get(client, org_a, f"/patients/{ready['patient']['id']}/consents").status_code == 403
    )  # no patient data


def test_consent_needs_published_wording(client: TestClient, org_a: H) -> None:
    recep = reception(client, org_a, "alpha-clinic")
    p = make_patient(client, recep)
    r = post(client, recep, URL.format(p["id"]), {"purpose": "AUDIO_RECORDING", "method": "PAPER"})
    assert r.status_code == 409 and "No consent wording" in r.json()["detail"]


def test_each_purpose_is_separate_and_recording_never_implies_training(
    client: TestClient, ready: dict[str, Any]
) -> None:
    pid = ready["patient"]["id"]
    grant(client, ready["recep"], pid, "AUDIO_RECORDING", "SPEECH_TRANSCRIPTION")
    s = status(client, ready["recep"], pid)
    assert s["AUDIO_RECORDING"]["active"] and s["SPEECH_TRANSCRIPTION"]["active"]
    for purpose in (
        "AI_PROCESSING",
        "AUDIO_RETENTION",
        "RESEARCH",
        "ANALYTICS",
        "AI_MODEL_IMPROVEMENT",
        "MEDICAL_CARE",
    ):
        assert s[purpose]["active"] is False, purpose
    dup = post(
        client, ready["recep"], URL.format(pid), {"purpose": "AUDIO_RECORDING", "method": "PAPER"}
    )
    assert dup.status_code == 409


def test_dependent_consents_need_their_parent(client: TestClient, ready: dict[str, Any]) -> None:
    pid, r = ready["patient"]["id"], ready["recep"]
    assert (
        post(
            client, r, URL.format(pid), {"purpose": "AUDIO_RETENTION", "method": "PAPER"}
        ).status_code
        == 409
    )
    assert (
        post(
            client, r, URL.format(pid), {"purpose": "AI_PROCESSING", "method": "PAPER"}
        ).status_code
        == 409
    )
    grant(client, r, pid, "SPEECH_TRANSCRIPTION", "AI_PROCESSING")
    assert status(client, r, pid)["AI_PROCESSING"]["active"]


def test_withdrawal_is_recorded_and_switches_dependents_off(
    client: TestClient, ready: dict[str, Any]
) -> None:
    pid, r = ready["patient"]["id"], ready["recep"]
    transcription = grant(client, r, pid, "SPEECH_TRANSCRIPTION", "AI_PROCESSING")[0]
    w = post(client, r, f"/consents/{transcription['id']}/withdraw", {"reason": "Changed my mind"})
    assert w.status_code == 200 and w.json()["status"] == "WITHDRAWN" and w.json()["withdrawn_at"]
    s = status(client, r, pid)
    assert s["SPEECH_TRANSCRIPTION"]["active"] is False
    assert (
        s["AI_PROCESSING"]["active"] is False
        and s["AI_PROCESSING"]["blocked_by"] == "SPEECH_TRANSCRIPTION"
    )
    assert post(client, r, f"/consents/{transcription['id']}/withdraw", {}).status_code == 409


def test_regranting_keeps_the_full_history(client: TestClient, ready: dict[str, Any]) -> None:
    pid, r = ready["patient"]["id"], ready["recep"]
    first = grant(client, r, pid, "RESEARCH")[0]
    post(client, r, f"/consents/{first['id']}/withdraw", {})
    second = grant(client, r, pid, "RESEARCH")[0]
    body = get(client, r, URL.format(pid)).json()
    assert [c["status"] for c in body["history"]] == ["GRANTED", "WITHDRAWN"]
    assert second["id"] != first["id"] and status(client, r, pid)["RESEARCH"]["active"]


def test_children_need_a_guardian_and_representatives_are_identified(
    client: TestClient, org_a: H
) -> None:
    install_wording(client, org_a)
    r = reception(client, org_a, "alpha-clinic")
    child = make_patient(client, r, "Baby Kumar", age_years=6)
    adult = make_patient(client, r, "Asha Rani", age_years=40, mobile="9123456780")
    assert get(client, r, URL.format(child["id"])).json()["guardian_required"] is True
    own = post(
        client, r, URL.format(child["id"]), {"purpose": "AUDIO_RECORDING", "method": "PAPER"}
    )
    assert own.status_code == 400 and "parent or guardian" in own.json()["detail"]
    anon = post(
        client,
        r,
        URL.format(child["id"]),
        {"purpose": "AUDIO_RECORDING", "method": "PAPER", "granted_by_type": "REPRESENTATIVE"},
    )
    assert anon.status_code == 422
    ok = grant(
        client,
        r,
        child["id"],
        "AUDIO_RECORDING",
        granted_by_type="REPRESENTATIVE",
        representative_name="Sunita Kumar",
        representative_relationship="Mother",
    )[0]
    assert ok["granted_by_type"] == "REPRESENTATIVE" and ok["representative_name"] == "Sunita Kumar"
    # A family member may also answer for an adult; it is recorded as such.
    fam = grant(
        client,
        r,
        adult["id"],
        "AUDIO_RECORDING",
        granted_by_type="REPRESENTATIVE",
        representative_name="Ravi",
        representative_relationship="Son",
    )[0]
    assert fam["granted_by_type"] == "REPRESENTATIVE"


def test_database_keeps_consent_history_intact(
    client: TestClient, ready: dict[str, Any], org_a: H
) -> None:
    c = grant(client, ready["recep"], ready["patient"]["id"], "RESEARCH")[0]
    maker = client.app.state.sessionmaker  # type: ignore[attr-defined]
    for sql in (
        "update consents set purpose = 'ANALYTICS'",
        "update consents set granted_by_type = 'PATIENT', policy_version = 99",
        "delete from consents",
        "update consent_policies set body = 'tampered'",
        "delete from consent_policies",
    ):
        with maker() as s:
            set_tenant(s, None, bypass=True)
            with pytest.raises(DBAPIError):
                s.execute(text(sql))
                s.commit()
    post(client, ready["recep"], f"/consents/{c['id']}/withdraw", {})
    with maker() as s:
        set_tenant(s, None, bypass=True)
        with pytest.raises(DBAPIError):  # a withdrawn consent is final
            s.execute(text("update consents set status = 'GRANTED'"))
            s.commit()


def test_role_matrix(client: TestClient, ready: dict[str, Any], org_a: H) -> None:
    pid = ready["patient"]["id"]
    for role in ("lab_technician", "billing_staff", "pharmacist", "radiology_technician"):
        h, _ = make_staff(client, org_a, f"{role}@alpha-clinic.example.com", role, "alpha-clinic")
        assert get(client, h, URL.format(pid)).status_code == 403, role
        assert (
            post(client, h, URL.format(pid), {"purpose": "RESEARCH", "method": "PAPER"}).status_code
            == 403
        )
    for role, purpose in (("doctor", "RESEARCH"), ("nurse", "ANALYTICS")):
        h, _ = make_staff(client, org_a, f"{role}@alpha-clinic.example.com", role, "alpha-clinic")
        assert get(client, h, URL.format(pid)).status_code == 200
        body = {"purpose": purpose, "method": "VERBAL_WITNESSED"}
        assert post(client, h, URL.format(pid), body).status_code == 201


def test_consent_is_tenant_isolated_and_audited_without_names(
    client: TestClient, ready: dict[str, Any], org_b: H
) -> None:
    pid = ready["patient"]["id"]
    c = grant(
        client,
        ready["recep"],
        pid,
        "AUDIO_RECORDING",
        granted_by_type="REPRESENTATIVE",
        representative_name="Zzyzx Guardian",
        representative_relationship="Aunt",
    )[0]
    rb = reception(client, org_b, "beta-hospital", "r@beta.example.com")
    assert get(client, rb, URL.format(pid)).status_code == 404
    assert post(client, rb, f"/consents/{c['id']}/withdraw", {}).status_code == 404
    audit = get(client, ready["admin"], "/audit-logs", limit=200).text.lower()
    assert "zzyzx" not in audit and "aunt" not in audit
    assert "CONSENT_GRANTED" in audit.upper()
    assert API
