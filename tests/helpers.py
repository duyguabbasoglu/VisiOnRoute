"""Shared test helpers."""

from __future__ import annotations

from fastapi.testclient import TestClient


def create_org_and_login(
    client: TestClient, slug: str, email: str, password: str = "GuvenliParola42!"
) -> dict[str, object]:
    """Register an organization and return the AuthResponse payload."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"Test Filo {slug}",
            "slug": slug,
            "email": email,
            "full_name": "Test Kullanıcı",
            "password": password,
        },
    )
    assert response.status_code == 201, response.text
    payload: dict[str, object] = response.json()
    return payload
