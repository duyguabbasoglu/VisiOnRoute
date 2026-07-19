"""M10: subscription limits, entitlements, platform admin."""

import os
import subprocess
import sys

from fastapi.testclient import TestClient

from tests.conftest import REPO_ROOT
from tests.helpers import create_org_and_login
from visionroute.config.settings import Settings


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def test_new_org_gets_trial_and_can_read_subscription(client: TestClient) -> None:
    owner = create_org_and_login(client, "saas-trial", "o@saas-trial.example")
    subscription = client.get("/api/v1/subscription", headers=_h(owner))
    assert subscription.status_code == 200
    body = subscription.json()
    assert body["plan_key"] == "baslangic"
    assert body["status"] == "trial"
    assert body["vehicle_limit"] == 10
    assert body["trial_ends_at"] is not None


def test_vehicle_limit_enforced(client: TestClient) -> None:
    owner = create_org_and_login(client, "saas-limit", "o@saas-limit.example")
    # Starter plan allows 10 vehicles.
    for i in range(10):
        created = client.post(
            "/api/v1/vehicles", json={"external_id": f"LIM-{i}"}, headers=_h(owner)
        )
        assert created.status_code == 201, created.text
    over = client.post("/api/v1/vehicles", json={"external_id": "LIM-11"}, headers=_h(owner))
    assert over.status_code == 409
    assert "Araç limiti aşıldı" in over.json()["error"]["message"]


def test_user_limit_enforced(client: TestClient) -> None:
    owner = create_org_and_login(client, "saas-users", "o@saas-users.example")
    # Starter plan allows 5 memberships; the owner already occupies one.
    for i in range(4):
        invitation = client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": f"u{i}@saas-users.example", "role": "analyst"},
            headers=_h(owner),
        ).json()
        accept = client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "token": invitation["invitation_token"],
                "full_name": f"Kullanıcı {i}",
                "password": "DavetliParola7!",
            },
        )
        assert accept.status_code == 201

    over = client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "fazla@saas-users.example", "role": "analyst"},
        headers=_h(owner),
    )
    assert over.status_code == 409
    assert "Kullanıcı limiti aşıldı" in over.json()["error"]["message"]


def _bootstrap_platform_admin(test_settings: Settings) -> None:
    env = {
        **os.environ,
        "VISIONROUTE_DATABASE_URL": test_settings.database_url,
        "VISIONROUTE_BOOTSTRAP_ADMIN_EMAIL": "platform@ornek.example",
        "VISIONROUTE_BOOTSTRAP_ADMIN_PASSWORD": "PlatformParola2026!",
    }
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "visionroute.cli.main",
            "admin",
            "bootstrap",
            "--full-name",
            "Platform Admin",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        check=False,  # "already exists" on reruns is fine
    )


def test_platform_admin_endpoints_and_rbac(client: TestClient, test_settings: Settings) -> None:
    owner = create_org_and_login(client, "saas-platform", "o@saas-platform.example")

    # A tenant owner must NOT reach platform endpoints.
    denied = client.get("/api/v1/platform/organizations", headers=_h(owner))
    assert denied.status_code == 403

    _bootstrap_platform_admin(test_settings)
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "platform@ornek.example", "password": "PlatformParola2026!"},
    )
    assert admin_login.status_code == 200
    admin = admin_login.json()
    assert admin["user"]["is_platform_admin"] is True

    organizations = client.get("/api/v1/platform/organizations", headers=_h(admin))
    assert organizations.status_code == 200
    org_row = next(o for o in organizations.json() if o["slug"] == "saas-platform")
    assert org_row["plan_key"] == "baslangic"

    # Plan upgrade by platform admin.
    changed = client.post(
        f"/api/v1/platform/organizations/{org_row['id']}/plan",
        json={"plan_key": "kurumsal"},
        headers=_h(admin),
    )
    assert changed.status_code == 200
    assert changed.json()["plan_key"] == "kurumsal"
    assert changed.json()["subscription_status"] == "active"

    # The tenant now sees unlimited vehicles.
    subscription = client.get("/api/v1/subscription", headers=_h(owner)).json()
    assert subscription["plan_key"] == "kurumsal"
    assert subscription["vehicle_limit"] == -1

    # Platform health endpoint responds with queue counters.
    health = client.get("/api/v1/platform/health", headers=_h(admin))
    assert health.status_code == 200
    assert set(health.json()) == {
        "outbox_pending",
        "outbox_dead_letter",
        "ingest_quarantined",
        "webhook_dead_letter",
    }
