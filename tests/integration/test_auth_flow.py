"""End-to-end auth flow against the real database and migrations."""

from fastapi.testclient import TestClient

from tests.helpers import create_org_and_login


def test_register_login_me_flow(client: TestClient) -> None:
    auth = create_org_and_login(client, "akyol-lojistik", "sahip@akyol.example")
    assert auth["user"]["role"] == "owner"  # type: ignore[index]
    token = auth["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "sahip@akyol.example"
    assert body["role_label"] == "Organizasyon Sahibi"
    assert body["organization_name"] == "Test Filo akyol-lojistik"


def test_login_rejects_wrong_password_uniformly(client: TestClient) -> None:
    create_org_and_login(client, "yanlis-parola", "user@yanlis.example")
    for email in ("user@yanlis.example", "yok@yanlis.example"):
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "YanlisParola99!"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert response.json()["error"]["message"] == "E-posta veya parola hatalı."


def test_refresh_rotation_and_reuse_detection(client: TestClient) -> None:
    create_org_and_login(client, "rotasyon", "r@rotasyon.example")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "r@rotasyon.example", "password": "GuvenliParola42!"},
    )
    first_refresh = login.cookies["vr_refresh"]

    # Rotation: old cookie exchanged for a new one.
    client.cookies.set("vr_refresh", first_refresh, path="/api/v1/auth")
    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    second_refresh = rotated.cookies["vr_refresh"]
    assert second_refresh != first_refresh

    # Reusing the rotated-out token must kill the whole family.
    client.cookies.set("vr_refresh", first_refresh, path="/api/v1/auth")
    reuse = client.post("/api/v1/auth/refresh")
    assert reuse.status_code == 401

    client.cookies.set("vr_refresh", second_refresh, path="/api/v1/auth")
    after_kill = client.post("/api/v1/auth/refresh")
    assert after_kill.status_code == 401
    client.cookies.clear()


def test_weak_password_rejected_in_turkish(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Zayıf Parola AŞ",
            "slug": "zayif-parola",
            "email": "z@zayif.example",
            "full_name": "Zayıf Deneme",
            "password": "kisa",
        },
    )
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "en az 12 karakter" in message


def test_account_lockout_after_repeated_failures(client: TestClient) -> None:
    create_org_and_login(client, "kilit-testi", "kilit@ornek.example")
    for _ in range(10):
        client.post(
            "/api/v1/auth/login",
            json={"email": "kilit@ornek.example", "password": "YanlisParola!!1"},
        )
    locked = client.post(
        "/api/v1/auth/login",
        json={"email": "kilit@ornek.example", "password": "GuvenliParola42!"},
    )
    assert locked.status_code == 403
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"
