"""RBAC enforcement, invitations, cross-tenant isolation, RLS, audit trail."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.helpers import create_org_and_login, invite_and_login
from visionroute.config.settings import Settings


def _headers(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


async def test_invitation_grants_role_and_rbac_enforced(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "rbac-filo", "sahip@rbac.example")
    analyst = await invite_and_login(
        client, test_settings, owner, "analist@rbac.example", "analyst"
    )
    assert analyst["user"]["role"] == "analyst"  # type: ignore[index]

    # Analyst may read the organization…
    read = client.get("/api/v1/organizations/current", headers=_headers(analyst))
    assert read.status_code == 200

    # …but must not update it, invite members, or manage roles.
    update = client.patch(
        "/api/v1/organizations/current",
        json={"name": "Yetkisiz Değişiklik"},
        headers=_headers(analyst),
    )
    assert update.status_code == 403
    assert update.json()["error"]["message"] == "Bu işlem için yetkiniz yok."

    invite = client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "x@rbac.example", "role": "analyst"},
        headers=_headers(analyst),
    )
    assert invite.status_code == 403


def test_unauthenticated_requests_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/organizations/current").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    garbage = client.get(
        "/api/v1/organizations/current", headers={"Authorization": "Bearer sahte-token"}
    )
    assert garbage.status_code == 401


def test_cross_tenant_object_access_denied(client: TestClient) -> None:
    org_a = create_org_and_login(client, "tenant-a", "a@tenant-a.example")
    org_b = create_org_and_login(client, "tenant-b", "b@tenant-b.example")

    members_b = client.get("/api/v1/organizations/current/members", headers=_headers(org_b))
    membership_b_id = members_b.json()[0]["membership_id"]

    # Org A's owner attacks org B's membership id directly (IDOR attempt).
    attack = client.patch(
        f"/api/v1/organizations/current/members/{membership_b_id}",
        json={"role": "analyst"},
        headers=_headers(org_a),
    )
    assert attack.status_code == 404

    delete_attack = client.delete(
        f"/api/v1/organizations/current/members/{membership_b_id}",
        headers=_headers(org_a),
    )
    assert delete_attack.status_code == 404

    # Members listing shows only own organization.
    members_a = client.get("/api/v1/organizations/current/members", headers=_headers(org_a)).json()
    emails = {m["email"] for m in members_a}
    assert "b@tenant-b.example" not in emails


def test_rls_blocks_unfiltered_cross_tenant_query(
    client: TestClient, test_settings: Settings
) -> None:
    """Even a WHERE-less query must only see the current tenant's rows (RLS)."""
    org_a = create_org_and_login(client, "rls-a", "a@rls.example")
    create_org_and_login(client, "rls-b", "b@rls.example")
    org_a_id = org_a["user"]["organization_id"]  # type: ignore[index]

    async def run() -> tuple[int, int]:
        engine = create_async_engine(test_settings.database_url)
        try:
            async with engine.connect() as conn:
                total = await conn.execute(
                    text(
                        "SELECT count(*) FROM (SELECT 1 FROM memberships "
                        "UNION ALL SELECT 1 FROM organization_settings) t"
                    )
                )
                # Without tenant context, RLS returns zero tenant rows.
                unscoped_count = int(total.scalar_one())

                await conn.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": str(org_a_id)},
                )
                scoped = await conn.execute(text("SELECT count(*) FROM memberships"))
                scoped_count = int(scoped.scalar_one())
                return unscoped_count, scoped_count
        finally:
            await engine.dispose()

    unscoped_count, scoped_count = asyncio.run(run())
    assert unscoped_count == 0
    assert scoped_count == 1  # only org A's single membership is visible


def test_audit_log_records_and_is_immutable(client: TestClient, test_settings: Settings) -> None:
    owner = create_org_and_login(client, "denetim", "audit@denetim.example")
    client.patch(
        "/api/v1/organizations/current",
        json={"name": "Denetim Filo A.Ş."},
        headers=_headers(owner),
    )

    async def run() -> None:
        engine = create_async_engine(test_settings.database_url)
        try:
            async with engine.connect() as conn:
                rows = await conn.execute(
                    text(
                        "SELECT action FROM audit_logs WHERE organization_id = :oid "
                        "ORDER BY created_at"
                    ),
                    {"oid": owner["user"]["organization_id"]},  # type: ignore[index]
                )
                actions = [r[0] for r in rows]
                assert "organization.registered" in actions
                assert "auth.login" in actions
                assert "organization.updated" in actions

                with pytest.raises(Exception, match="append-only"):
                    await conn.execute(text("UPDATE audit_logs SET action = 'kurcalandi'"))
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_owner_role_cannot_be_removed_or_reassigned(client: TestClient) -> None:
    owner = create_org_and_login(client, "sahiplik", "sahip@sahiplik.example")
    members = client.get("/api/v1/organizations/current/members", headers=_headers(owner)).json()
    owner_membership_id = members[0]["membership_id"]

    demote = client.patch(
        f"/api/v1/organizations/current/members/{owner_membership_id}",
        json={"role": "analyst"},
        headers=_headers(owner),
    )
    assert demote.status_code == 409

    remove = client.delete(
        f"/api/v1/organizations/current/members/{owner_membership_id}",
        headers=_headers(owner),
    )
    assert remove.status_code == 409


def test_nonexistent_membership_returns_404(client: TestClient) -> None:
    owner = create_org_and_login(client, "yok-uye", "y@yok-uye.example")
    response = client.delete(
        f"/api/v1/organizations/current/members/{uuid.uuid4()}",
        headers=_headers(owner),
    )
    assert response.status_code == 404
