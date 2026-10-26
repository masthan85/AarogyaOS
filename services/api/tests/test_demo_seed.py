from fastapi.testclient import TestClient

from app.core.config import Settings
from app.demo_seed import PASSWORD, SLUG, run
from app.main import create_app


def test_demo_data_is_created_once_and_the_accounts_work(settings: Settings) -> None:
    assert run(settings) == 0
    assert run(settings) == 0  # a second run changes nothing and does not fail
    with TestClient(create_app(settings)) as client:
        for email in (
            "admin@demo.example.com",
            "doctor@demo.example.com",
            "nurse@demo.example.com",
            "reception@demo.example.com",
            "pharmacist@demo.example.com",
            "lab@demo.example.com",
        ):
            r = client.post(
                "/api/v1/auth/login",
                json={"organisation_slug": SLUG, "email": email, "password": PASSWORD},
            )
            assert r.status_code == 200, (email, r.text)
        admin = client.post(
            "/api/v1/auth/login",
            json={
                "organisation_slug": SLUG,
                "email": "admin@demo.example.com",
                "password": PASSWORD,
            },
        ).json()
        h = {"Authorization": f"Bearer {admin['access_token']}"}
        policy = client.get("/api/v1/organisations/current/policy", headers=h).json()
        assert policy["recording_enabled"] and policy["ai_processing_enabled"]
        assert len(client.get("/api/v1/practitioners", headers=h).json()) == 1


def test_it_refuses_to_run_in_production(settings: Settings) -> None:
    prod = settings.model_copy(update={"environment": "production"})
    assert run(prod) == 1
