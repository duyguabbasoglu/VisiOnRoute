"""Fleet domain: CRUD, RBAC, cross-tenant isolation, uniqueness, assignments."""

from fastapi.testclient import TestClient

from tests.helpers import create_org_and_login, invite_and_login
from visionroute.config.settings import Settings


def _h(auth: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def test_vehicle_and_driver_crud(client: TestClient) -> None:
    owner = create_org_and_login(client, "filo-crud", "o@filo-crud.example")

    vehicle = client.post(
        "/api/v1/vehicles",
        json={"external_id": "34ABC123", "plate": "34 ABC 123", "make": "Ford", "year": 2022},
        headers=_h(owner),
    )
    assert vehicle.status_code == 201, vehicle.text
    vehicle_id = vehicle.json()["id"]

    driver = client.post(
        "/api/v1/drivers",
        json={"external_id": "SUR-001", "full_name": "Ahmet Yılmaz", "phone": "5551112233"},
        headers=_h(owner),
    )
    assert driver.status_code == 201
    driver_id = driver.json()["id"]

    listing = client.get("/api/v1/vehicles", headers=_h(owner)).json()
    assert listing["pagination"]["total"] == 1
    assert listing["items"][0]["id"] == vehicle_id

    detail = client.get(f"/api/v1/vehicles/{vehicle_id}", headers=_h(owner))
    assert detail.status_code == 200
    assert detail.json()["make"] == "Ford"

    updated = client.patch(
        f"/api/v1/vehicles/{vehicle_id}",
        json={"status": "maintenance", "label": "Bakımda"},
        headers=_h(owner),
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "maintenance"
    assert driver_id  # created above


def test_duplicate_external_id_conflict(client: TestClient) -> None:
    owner = create_org_and_login(client, "cift-kayit", "o@cift.example")
    payload = {"external_id": "DUP-1"}
    assert client.post("/api/v1/vehicles", json=payload, headers=_h(owner)).status_code == 201
    dup = client.post("/api/v1/vehicles", json=payload, headers=_h(owner))
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "CONFLICT"


async def test_fleet_read_permission_but_not_manage(
    client: TestClient, test_settings: Settings
) -> None:
    owner = create_org_and_login(client, "filo-rbac", "o@filo-rbac.example")
    analyst = await invite_and_login(
        client, test_settings, owner, "analist@filo-rbac.example", "analyst"
    )

    # Analyst can read but not create.
    assert client.get("/api/v1/vehicles", headers=_h(analyst)).status_code == 200
    create = client.post("/api/v1/vehicles", json={"external_id": "X-1"}, headers=_h(analyst))
    assert create.status_code == 403


def test_cross_tenant_vehicle_isolation(client: TestClient) -> None:
    org_a = create_org_and_login(client, "filo-a", "a@filo-a.example")
    org_b = create_org_and_login(client, "filo-b", "b@filo-b.example")

    created = client.post("/api/v1/vehicles", json={"external_id": "GIZLI-1"}, headers=_h(org_b))
    vehicle_b_id = created.json()["id"]

    # Org A cannot read org B's vehicle by id, and its list stays empty.
    assert client.get(f"/api/v1/vehicles/{vehicle_b_id}", headers=_h(org_a)).status_code == 404
    assert client.get("/api/v1/vehicles", headers=_h(org_a)).json()["pagination"]["total"] == 0


def test_driver_assignment_lifecycle_and_single_open_rule(client: TestClient) -> None:
    owner = create_org_and_login(client, "atama", "o@atama.example")
    vehicle_id = client.post(
        "/api/v1/vehicles", json={"external_id": "ARC-1"}, headers=_h(owner)
    ).json()["id"]
    driver1 = client.post(
        "/api/v1/drivers", json={"external_id": "D1", "full_name": "Sürücü Bir"}, headers=_h(owner)
    ).json()["id"]
    driver2 = client.post(
        "/api/v1/drivers", json={"external_id": "D2", "full_name": "Sürücü İki"}, headers=_h(owner)
    ).json()["id"]

    first = client.post(
        "/api/v1/assignments",
        json={"driver_id": driver1, "vehicle_id": vehicle_id},
        headers=_h(owner),
    )
    assert first.status_code == 201
    assignment_id = first.json()["id"]

    # A second open assignment for the same vehicle must be rejected.
    conflict = client.post(
        "/api/v1/assignments",
        json={"driver_id": driver2, "vehicle_id": vehicle_id},
        headers=_h(owner),
    )
    assert conflict.status_code == 409

    # Close the first, then the second is allowed.
    closed = client.post(f"/api/v1/assignments/{assignment_id}/close", headers=_h(owner))
    assert closed.status_code == 200
    assert closed.json()["ended_at"] is not None

    second = client.post(
        "/api/v1/assignments",
        json={"driver_id": driver2, "vehicle_id": vehicle_id},
        headers=_h(owner),
    )
    assert second.status_code == 201


def test_device_and_camera_registration(client: TestClient) -> None:
    owner = create_org_and_login(client, "cihaz", "o@cihaz.example")
    vehicle_id = client.post(
        "/api/v1/vehicles", json={"external_id": "V-DEV"}, headers=_h(owner)
    ).json()["id"]

    device = client.post(
        "/api/v1/devices",
        json={"external_id": "DEV-1", "kind": "dashcam", "vehicle_id": vehicle_id},
        headers=_h(owner),
    )
    assert device.status_code == 201
    device_id = device.json()["id"]

    camera = client.post(
        "/api/v1/cameras",
        json={
            "external_id": "CAM-1",
            "position": "road",
            "device_id": device_id,
            "vehicle_id": vehicle_id,
        },
        headers=_h(owner),
    )
    assert camera.status_code == 201
    assert camera.json()["position"] == "road"

    cameras = client.get("/api/v1/cameras", headers=_h(owner)).json()
    assert len(cameras) == 1


def test_device_and_camera_update(client: TestClient) -> None:
    owner = create_org_and_login(client, "cihaz-guncel", "o@cihaz-guncel.example")
    other = create_org_and_login(client, "cihaz-diger", "o@cihaz-diger.example")
    vehicle_id = client.post(
        "/api/v1/vehicles", json={"external_id": "V-UPD"}, headers=_h(owner)
    ).json()["id"]
    device_id = client.post(
        "/api/v1/devices", json={"external_id": "DEV-UPD"}, headers=_h(owner)
    ).json()["id"]

    updated = client.patch(
        f"/api/v1/devices/{device_id}",
        json={"status": "inactive", "vehicle_id": vehicle_id, "label": "Ön ünite"},
        headers=_h(owner),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "inactive"
    assert updated.json()["vehicle_id"] == vehicle_id
    assert updated.json()["label"] == "Ön ünite"

    # Platform-owned statuses and explicit nulls are rejected.
    for bad in ({"status": "offline"}, {"status": None}):
        rejected = client.patch(f"/api/v1/devices/{device_id}", json=bad, headers=_h(owner))
        assert rejected.status_code == 422, rejected.text

    camera_id = client.post(
        "/api/v1/cameras",
        json={"external_id": "CAM-UPD", "vehicle_id": vehicle_id},
        headers=_h(owner),
    ).json()["id"]
    camera = client.patch(
        f"/api/v1/cameras/{camera_id}",
        json={"device_id": device_id, "status": "inactive", "vehicle_id": None},
        headers=_h(owner),
    )
    assert camera.status_code == 200, camera.text
    assert camera.json()["device_id"] == device_id
    assert camera.json()["vehicle_id"] is None
    assert camera.json()["status"] == "inactive"

    # Another tenant can neither update the records nor attach its own vehicle.
    foreign = client.patch(
        f"/api/v1/devices/{device_id}", json={"status": "active"}, headers=_h(other)
    )
    assert foreign.status_code == 404
    foreign_vehicle = client.post(
        "/api/v1/vehicles", json={"external_id": "V-DIGER"}, headers=_h(other)
    ).json()["id"]
    cross = client.patch(
        f"/api/v1/cameras/{camera_id}", json={"vehicle_id": foreign_vehicle}, headers=_h(owner)
    )
    assert cross.status_code == 404


def test_assigning_foreign_vehicle_returns_404(client: TestClient) -> None:
    org_a = create_org_and_login(client, "carpi-a", "a@carpi.example")
    org_b = create_org_and_login(client, "carpi-b", "b@carpi.example")
    vehicle_b = client.post(
        "/api/v1/vehicles", json={"external_id": "VB"}, headers=_h(org_b)
    ).json()["id"]
    driver_a = client.post(
        "/api/v1/drivers", json={"external_id": "DA", "full_name": "Sürücü A"}, headers=_h(org_a)
    ).json()["id"]

    # Org A tries to assign its driver to org B's vehicle.
    resp = client.post(
        "/api/v1/assignments",
        json={"driver_id": driver_a, "vehicle_id": vehicle_b},
        headers=_h(org_a),
    )
    assert resp.status_code == 404
