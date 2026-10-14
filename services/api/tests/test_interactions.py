from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.clinical_helpers import Visit, get, make_visit, post
from tests.conftest import make_staff
from tests.speech_helpers import (
    create_session,
    enable_recording,
    grant,
    install_wording,
    put,
    recording_ready,
    start_session,
)

H = dict[str, str]


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return recording_ready(client, org_a)


# ---- preconditions -----------------------------------------------------------------


def test_recording_is_off_until_an_administrator_turns_it_on(client: TestClient, org_a: H) -> None:
    visit = make_visit(client, org_a, stage="consult")
    install_wording(client, org_a)
    grant(client, visit.recep, visit.patient["id"], "AUDIO_RECORDING", "SPEECH_TRANSCRIPTION")
    r = create_session(client, visit)
    assert r.status_code == 409 and "not enabled" in r.json()["detail"]


def test_missing_consent_blocks_recording_and_names_what_is_missing(
    client: TestClient, org_a: H
) -> None:
    visit = make_visit(client, org_a, stage="consult")
    enable_recording(client, org_a)
    install_wording(client, org_a)
    grant(client, visit.recep, visit.patient["id"], "AUDIO_RECORDING")
    r = create_session(client, visit)
    assert r.status_code == 409 and r.json()["title"] == "consent_required"
    assert r.json()["missing"] == ["SPEECH_TRANSCRIPTION"]


def test_ai_processing_needs_both_the_org_switch_and_the_patients_consent(
    client: TestClient, org_a: H, v: Visit
) -> None:
    assert create_session(client, v, ai_processing=True).status_code == 409  # org has AI off
    enable_recording(client, org_a, ai=True)
    r = create_session(client, v, ai_processing=True)
    assert r.status_code == 409 and r.json()["missing"] == ["AI_PROCESSING"]
    grant(client, v.recep, v.patient["id"], "AI_PROCESSING")
    assert create_session(client, v, ai_processing=True).status_code == 201


def test_only_the_right_person_can_record_each_kind_of_conversation(
    client: TestClient, v: Visit, org_a: H
) -> None:
    body = {"patient_id": v.patient["id"], "purpose": "CONSULTATION", "encounter_id": v.enc_id}
    for h in (v.nurse, v.recep, v.admin):
        assert post(client, h, "/interactions", body).status_code == 403
    from tests.helpers import make_practitioner

    other_doc, _ = make_practitioner(
        client, org_a, "alpha-clinic", v.facility, "dr.other@x.example.com"
    )
    assert (
        post(client, other_doc, "/interactions", body).status_code == 403
    )  # not this patient's doctor
    triage = {"patient_id": v.patient["id"], "purpose": "TRIAGE", "encounter_id": v.enc_id}
    assert post(client, v.doctor, "/interactions", triage).status_code == 403
    assert post(client, v.nurse, "/interactions", triage).status_code == 201


def test_visit_binding_rules(client: TestClient, v: Visit) -> None:
    no_visit = post(
        client,
        v.doctor,
        "/interactions",
        {"patient_id": v.patient["id"], "purpose": "CONSULTATION"},
    )
    assert no_visit.status_code == 400
    wrong_link = post(
        client,
        v.recep,
        "/interactions",
        {"patient_id": v.patient["id"], "purpose": "RECEPTION", "encounter_id": v.enc_id},
    )
    assert wrong_link.status_code == 400
    missing = "00000000-0000-4000-8000-000000000000"
    stranger = post(
        client,
        v.doctor,
        "/interactions",
        {"patient_id": v.patient["id"], "purpose": "CONSULTATION", "encounter_id": missing},
    )
    assert stranger.status_code == 404
    # The visit is already with the doctor, so it is no longer a reception conversation.
    late = post(
        client,
        v.recep,
        "/interactions",
        {"patient_id": v.patient["id"], "purpose": "RECEPTION", "appointment_id": v.appt_id},
    )
    assert late.status_code == 409


def test_reception_recordings_bind_to_the_open_visit_not_an_encounter(
    client: TestClient, org_a: H
) -> None:
    visit = make_visit(client, org_a)  # checked in, at triage: still a reception-stage visit
    enable_recording(client, org_a)
    install_wording(client, org_a)
    grant(client, visit.recep, visit.patient["id"], "AUDIO_RECORDING", "SPEECH_TRANSCRIPTION")
    r = post(
        client,
        visit.recep,
        "/interactions",
        {
            "patient_id": visit.patient["id"],
            "purpose": "RECEPTION",
            "appointment_id": visit.appt_id,
        },
    )
    assert (
        r.status_code == 201
        and r.json()["encounter_id"] is None
        and r.json()["appointment_id"] == visit.appt_id
    )


def test_a_triage_only_encounter_cannot_be_recorded_as_a_consultation(
    client: TestClient, org_a: H
) -> None:
    visit = make_visit(client, org_a)  # triage stage only
    enable_recording(client, org_a)
    install_wording(client, org_a)
    grant(client, visit.recep, visit.patient["id"], "AUDIO_RECORDING", "SPEECH_TRANSCRIPTION")
    r = create_session(client, visit)
    assert r.status_code == 409 and "not started" in r.json()["detail"]


def test_unavailable_providers_give_a_clear_error_not_a_silent_fallback(
    client: TestClient, v: Visit
) -> None:
    client.app.state.settings.speech_provider = "sarvam"  # type: ignore[attr-defined]
    r = create_session(client, v)
    assert r.status_code == 503 and "could not be read" in r.json()["detail"]
    client.app.state.settings.speech_provider = ""  # type: ignore[attr-defined]
    assert create_session(client, v).status_code == 503


def test_production_refuses_the_development_provider(client: TestClient, v: Visit) -> None:
    client.app.state.settings.environment = "production"  # type: ignore[attr-defined]
    try:
        r = create_session(client, v)
    finally:
        client.app.state.settings.environment = "test"  # type: ignore[attr-defined]
    assert r.status_code == 503 and "disabled in production" in r.json()["detail"]


def test_one_recording_at_a_time_per_person_and_per_visit(client: TestClient, v: Visit) -> None:
    first = start_session(client, v)
    assert create_session(client, v).status_code == 409
    post(client, v.doctor, f"/interactions/{first['interaction']['id']}/stop")
    assert create_session(client, v).status_code == 201


# ---- lifecycle ---------------------------------------------------------------------


def test_explicit_start_pause_resume_stop_with_events(client: TestClient, v: Visit) -> None:
    created = create_session(client, v).json()
    assert created["status"] == "CREATED" and created["is_development"] is True
    assert created["speech_provider"] == "development" and created["retain_audio"] is False
    iid = created["id"]
    started = post(client, v.doctor, f"/interactions/{iid}/start").json()
    assert started["interaction"]["status"] == "ACTIVE"
    assert started["audio_format"] == {
        "encoding": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "max_frame_bytes": 65536,
    }
    assert started["gateway_path"].endswith(f"/{iid}/audio") and started["auth"] == "first_message"
    assert post(client, v.doctor, f"/interactions/{iid}/start").status_code == 409
    assert post(client, v.doctor, f"/interactions/{iid}/pause").json()["status"] == "PAUSED"
    assert post(client, v.doctor, f"/interactions/{iid}/pause").status_code == 409
    assert post(client, v.doctor, f"/interactions/{iid}/resume").json()["status"] == "ACTIVE"
    stopped = post(client, v.doctor, f"/interactions/{iid}/stop").json()
    assert stopped["status"] == "ENDED" and stopped["end_reason"] == "USER" and stopped["ended_at"]
    assert (
        post(client, v.doctor, f"/interactions/{iid}/stop").json()["status"] == "ENDED"
    )  # idempotent
    kinds = [
        e["event_type"]
        for e in get(client, v.doctor, f"/patients/{v.patient['id']}/timeline").json()
    ]
    for expected in (
        "INTERACTION_STARTED",
        "RECORDING_STARTED",
        "RECORDING_PAUSED",
        "RECORDING_RESUMED",
        "RECORDING_STOPPED",
        "TRANSCRIPT_UPDATED",
    ):
        assert expected in kinds, expected


def test_only_the_person_who_set_up_the_recording_controls_it(client: TestClient, v: Visit) -> None:
    iid = create_session(client, v).json()["id"]
    for h in (v.nurse, v.recep, v.admin):
        assert (
            post(client, h, f"/interactions/{iid}/start").status_code == 404
        )  # existence not revealed
        assert get(client, h, f"/interactions/{iid}").status_code == 404
    assert get(client, v.doctor, f"/interactions/{iid}").status_code == 200


def test_a_recording_set_up_before_consent_was_withdrawn_cannot_be_started(
    client: TestClient, v: Visit
) -> None:
    iid = create_session(client, v).json()["id"]
    history = get(client, v.recep, f"/patients/{v.patient['id']}/consents").json()["history"]
    consent = next(c for c in history if c["purpose"] == "AUDIO_RECORDING")
    post(client, v.recep, f"/consents/{consent['id']}/withdraw", {"reason": "Not comfortable"})
    r = post(client, v.doctor, f"/interactions/{iid}/start")
    assert r.status_code == 409 and "consent was withdrawn" in r.json()["detail"]
    assert get(client, v.doctor, f"/interactions/{iid}").json()["end_reason"] == "CONSENT_WITHDRAWN"
    again = create_session(client, v)  # and a brand new one is refused too
    assert again.json()["title"] == "consent_required", again.text


def test_withdrawing_consent_ends_a_live_recording_immediately(
    client: TestClient, v: Visit
) -> None:
    iid = start_session(client, v)["interaction"]["id"]
    consent = next(
        c
        for c in get(client, v.recep, f"/patients/{v.patient['id']}/consents").json()["history"]
        if c["purpose"] == "SPEECH_TRANSCRIPTION"
    )
    w = post(client, v.recep, f"/consents/{consent['id']}/withdraw", {})
    assert w.status_code == 200
    ia = get(client, v.doctor, f"/interactions/{iid}").json()
    assert ia["status"] == "ENDED" and ia["end_reason"] == "CONSENT_WITHDRAWN"
    ev = next(
        e
        for e in get(client, v.doctor, f"/patients/{v.patient['id']}/timeline").json()
        if e["event_type"] == "CONSENT_WITHDRAWN"
    )
    assert ev["payload"]["sessions_ended"] == 1
    assert create_session(client, v).status_code == 409  # and a new one is refused


def test_withdrawing_ai_consent_ends_only_ai_sessions(client: TestClient, org_a: H) -> None:
    v = recording_ready(client, org_a, ai=True)
    plain = start_session(client, v)["interaction"]["id"]
    post(client, v.doctor, f"/interactions/{plain}/stop")
    ai = start_session(client, v, ai_processing=True)["interaction"]["id"]
    consent = next(
        c
        for c in get(client, v.recep, f"/patients/{v.patient['id']}/consents").json()["history"]
        if c["purpose"] == "AI_PROCESSING"
    )
    post(client, v.recep, f"/consents/{consent['id']}/withdraw", {})
    assert get(client, v.doctor, f"/interactions/{ai}").json()["end_reason"] == "CONSENT_WITHDRAWN"
    assert get(client, v.doctor, f"/interactions/{plain}").json()["end_reason"] == "USER"
    assert create_session(client, v).status_code == 201  # recording without AI is still allowed


def test_a_session_whose_audio_stopped_arriving_stops_claiming_to_record(
    client: TestClient, v: Visit, db: Session
) -> None:
    iid = start_session(client, v)["interaction"]["id"]
    db.execute(
        text("update clinical_interactions set last_audio_at = :t"),
        {"t": datetime.now(UTC) - timedelta(minutes=5)},
    )
    db.commit()
    ia = get(client, v.doctor, f"/interactions/{iid}").json()
    assert ia["status"] == "PAUSED" and ia["pause_reason"] == "CONNECTION_LOST"


# ---- transcripts, speakers, privacy ------------------------------------------------


def test_transcript_access_is_limited_to_participants(
    client: TestClient, v: Visit, org_a: H
) -> None:
    iid = start_session(client, v)["interaction"]["id"]
    assert get(client, v.doctor, f"/interactions/{iid}/transcript").status_code == 200
    assert (
        get(client, v.nurse, f"/interactions/{iid}/transcript").status_code == 404
    )  # did not take part
    assert get(client, v.admin, f"/interactions/{iid}/transcript").status_code == 403
    lab, _ = make_staff(
        client, org_a, "lab@alpha-clinic.example.com", "lab_technician", "alpha-clinic"
    )
    assert get(client, lab, f"/interactions/{iid}/transcript").status_code == 403


def test_a_reception_recording_is_not_visible_to_the_doctor(client: TestClient, org_a: H) -> None:
    visit = make_visit(client, org_a)
    enable_recording(client, org_a)
    install_wording(client, org_a)
    grant(client, visit.recep, visit.patient["id"], "AUDIO_RECORDING", "SPEECH_TRANSCRIPTION")
    body = {
        "patient_id": visit.patient["id"],
        "purpose": "RECEPTION",
        "appointment_id": visit.appt_id,
    }
    r = post(client, visit.recep, "/interactions", body)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    assert get(client, visit.doctor, f"/interactions/{iid}/transcript").status_code == 404
    assert get(client, visit.recep, f"/interactions/{iid}/transcript").status_code == 200


def test_opening_a_transcript_is_audited_but_polling_is_not(client: TestClient, v: Visit) -> None:
    iid = start_session(client, v)["interaction"]["id"]
    get(client, v.doctor, f"/interactions/{iid}/transcript", after_seq=0)
    for _ in range(5):
        get(client, v.doctor, f"/interactions/{iid}/transcript", after_seq=3)
    assert len(get(client, v.admin, "/audit-logs", action="TRANSCRIPT_VIEWED").json()) == 1


def test_speaker_roles_start_unknown_and_must_be_assigned_by_a_person(
    client: TestClient, v: Visit, db: Session
) -> None:
    from app.modules.interactions.models import InteractionSpeaker

    iid = start_session(client, v)["interaction"]["id"]
    assert get(client, v.doctor, f"/interactions/{iid}/transcript").json()["speakers"] == []
    org_id = db.execute(text("select organisation_id from clinical_interactions")).scalar_one()
    db.add(
        InteractionSpeaker(
            interaction_id=iid, speaker_id="spk_0", organisation_id=org_id, role="UNKNOWN"
        )
    )
    db.commit()
    url = f"/interactions/{iid}/speakers/spk_0"
    assert put(client, v.doctor, url, {"role": "BOGUS"}).status_code == 422
    assert (
        put(client, v.doctor, f"/interactions/{iid}/speakers/spk_9", {"role": "DOCTOR"}).status_code
        == 404
    )
    done = put(client, v.doctor, url, {"role": "FAMILY_MEMBER", "label": "Patient's son"})
    assert done.status_code == 200 and done.json()["role"] == "FAMILY_MEMBER"
    log = get(client, v.admin, "/audit-logs", action="SPEAKER_ROLE_ASSIGNED").json()[0]
    assert log["before"]["role"] == "UNKNOWN" and log["after"]["role"] == "FAMILY_MEMBER"
    assert put(client, v.recep, url, {"role": "DOCTOR"}).status_code == 403


def test_recordings_are_tenant_isolated(client: TestClient, v: Visit, org_b: H) -> None:
    iid = start_session(client, v)["interaction"]["id"]
    doc_b, _ = make_staff(client, org_b, "dr@beta.example.com", "doctor", "beta-hospital")
    assert get(client, doc_b, f"/interactions/{iid}").status_code == 404
    assert get(client, doc_b, f"/interactions/{iid}/transcript").status_code == 404
    assert post(client, doc_b, f"/interactions/{iid}/stop").status_code == 404
    assert get(client, doc_b, f"/patients/{v.patient['id']}/interactions").json() == []


def test_session_metadata_is_audited_without_content(client: TestClient, v: Visit) -> None:
    start_session(client, v)
    actions = {a["action"] for a in get(client, v.admin, "/audit-logs", limit=200).json()}
    assert {"INTERACTION_CREATED", "INTERACTION_STARTED", "RECORDING_STARTED"} <= actions
