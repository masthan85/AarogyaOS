from fastapi.testclient import TestClient

from tests.clinical_helpers import get
from tests.conftest import make_staff
from tests.speech_helpers import put


def test_defaults_are_privacy_protective(client: TestClient, org_a: dict[str, str]) -> None:
    p = get(client, org_a, "/organisations/current/policy").json()
    assert p["recording_enabled"] is False and p["ai_processing_enabled"] is False
    assert p["audio_retention"] == "DISCARD_AFTER_TRANSCRIPTION"


def test_policy_changes_need_org_manage_and_are_audited_as_diffs(
    client: TestClient, org_a: dict[str, str]
) -> None:
    doc, _ = make_staff(client, org_a, "dr@alpha-clinic.example.com", "doctor", "alpha-clinic")
    assert (
        put(client, doc, "/organisations/current/policy", {"recording_enabled": True}).status_code
        == 403
    )
    assert (
        put(client, org_a, "/organisations/current/policy", {"recording_enabled": True}).status_code
        == 200
    )
    log = get(client, org_a, "/audit-logs", action="ORG_POLICY_UPDATED").json()[0]
    assert log["before"] == {"recording_enabled": False} and log["after"] == {
        "recording_enabled": True
    }


def test_audio_cannot_be_retained_when_recording_is_off(
    client: TestClient, org_a: dict[str, str]
) -> None:
    r = put(
        client,
        org_a,
        "/organisations/current/policy",
        {"audio_retention": "RETAIN_DAYS", "recording_enabled": False},
    )
    assert r.status_code == 422
    assert (
        put(client, org_a, "/organisations/current/policy", {"retain_days": 0}).status_code == 422
    )


def test_language_catalogue_is_data_driven_and_covers_the_indian_languages(
    client: TestClient, org_a: dict[str, str]
) -> None:
    langs = {x["tag"]: x for x in get(client, org_a, "/languages").json()}
    assert len(langs) >= 13
    assert {
        "hi-IN",
        "te-IN",
        "ta-IN",
        "kn-IN",
        "ml-IN",
        "mr-IN",
        "bn-IN",
        "gu-IN",
        "pa-IN",
        "ur-IN",
        "or-IN",
        "as-IN",
        "en-IN",
    } <= set(langs)
    assert langs["te-IN"]["native_name"] == "తెలుగు" and langs["pa-IN"]["script"] == "Gurmukhi"
    assert langs["kn-IN"]["provider_support"] == {}  # no provider has been measured for it: say so


def test_an_organisation_can_restrict_its_languages(
    client: TestClient, org_a: dict[str, str]
) -> None:
    put(client, org_a, "/organisations/current/policy", {"enabled_languages": ["te-IN", "en-IN"]})
    assert {x["tag"] for x in get(client, org_a, "/languages").json()} == {"te-IN", "en-IN"}


def test_languages_need_a_login(client: TestClient) -> None:
    assert client.get("/api/v1/languages").status_code == 401


def test_policy_is_per_organisation(
    client: TestClient, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    put(client, org_a, "/organisations/current/policy", {"recording_enabled": True})
    assert get(client, org_b, "/organisations/current/policy").json()["recording_enabled"] is False
