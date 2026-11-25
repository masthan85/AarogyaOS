"""An organisation can require two-step sign-in for chosen roles. Someone in such a role without it
can sign in, but can do nothing except set it up, and cannot switch it off once it is on."""

from typing import Any

from fastapi.testclient import TestClient

from app.core import totp
from tests.clinical_helpers import get, post
from tests.conftest import make_staff
from tests.speech_helpers import put
from tests.test_mfa import enrol

H = dict[str, str]
ORG = "alpha-clinic"


def require_for(client: TestClient, admin: H, roles: list[str]) -> Any:
    current = get(client, admin, "/organisations/current/policy").json()
    return put(
        client, admin, "/organisations/current/policy", {**current, "mfa_required_roles": roles}
    )


def test_a_required_role_can_do_nothing_until_two_step_sign_in_is_set_up(
    client: TestClient, org_a: H
) -> None:
    doctor, _ = make_staff(client, org_a, "doc-mfa@alpha-clinic.example.com", "doctor", ORG)
    nurse, _ = make_staff(client, org_a, "nurse-mfa@alpha-clinic.example.com", "nurse", ORG)

    assert require_for(client, org_a, ["doctor"]).status_code == 200

    me = get(client, doctor, "/auth/me").json()
    assert me["mfa_setup_required"] is True
    blocked = get(client, doctor, "/facilities")
    assert blocked.status_code == 403 and blocked.json()["title"] == "mfa_setup_required"
    # Roles not on the list carry on as before.
    assert get(client, nurse, "/auth/me").json()["mfa_setup_required"] is False
    assert get(client, nurse, "/facilities").status_code == 200

    # Setting it up is still possible, and once it is on everything opens again.
    secret, _codes = enrol(client, doctor)
    assert get(client, doctor, "/auth/me").json()["mfa_setup_required"] is False
    assert get(client, doctor, "/facilities").status_code == 200

    # It cannot be switched off while the clinic requires it.
    code = totp.code_at(secret, totp.current_step() + 1)
    refused = post(
        client, doctor, "/auth/mfa/disable", {"password": "correct-horse-battery", "code": code}
    )
    assert refused.status_code == 409


def test_the_audio_socket_is_refused_too(client: TestClient, org_a: H) -> None:
    doctor, _ = make_staff(client, org_a, "doc-ws@alpha-clinic.example.com", "doctor", ORG)
    require_for(client, org_a, ["doctor"])
    token = doctor["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(
        "/api/v1/interactions/00000000-0000-0000-0000-000000000000/audio"
    ) as ws:
        ws.send_json({"type": "auth", "token": token})
        msg = ws.receive_json()
    assert msg == {"type": "stopped", "reason": "two-step sign-in required"}


def test_only_real_clinic_roles_can_be_required(client: TestClient, org_a: H) -> None:
    assert require_for(client, org_a, ["surgeon"]).status_code == 422
    assert require_for(client, org_a, ["super_admin"]).status_code == 422  # a platform role
    ok = require_for(client, org_a, ["nurse", "doctor", "nurse"])
    assert ok.status_code == 200 and ok.json()["mfa_required_roles"] == ["doctor", "nurse"]


def test_an_administrator_requiring_it_for_their_own_role_is_not_locked_out_of_setting_it_up(
    client: TestClient, org_a: H
) -> None:
    assert require_for(client, org_a, ["hospital_admin"]).status_code == 200
    assert get(client, org_a, "/auth/me").json()["mfa_setup_required"] is True
    assert get(client, org_a, "/organisations/current/policy").status_code == 403
    enrol(client, org_a)
    assert get(client, org_a, "/organisations/current/policy").status_code == 200


def test_screen_protection_is_on_by_default_and_a_clinic_can_turn_it_off(
    client: TestClient, org_a: H
) -> None:
    nurse, _ = make_staff(client, org_a, "nurse-screen@alpha-clinic.example.com", "nurse", ORG)
    assert get(client, nurse, "/auth/me").json()["protect_screens"] is True
    current = get(client, org_a, "/organisations/current/policy").json()
    assert current["protect_screens"] is True
    r = put(client, org_a, "/organisations/current/policy", {**current, "protect_screens": False})
    assert r.status_code == 200, r.text
    assert get(client, nurse, "/auth/me").json()["protect_screens"] is False
