import jwt
from fastapi.testclient import TestClient

from app.main import JWT_ALGORITHM, JWT_SECRET, _DEAD_LETTER_QUEUE, _TENANT_CONFIGS, app

client = TestClient(app)


def _make_token(roles):
    return jwt.encode({"sub": "parv", "roles": roles}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def setup_function():
    _TENANT_CONFIGS.clear()
    _DEAD_LETTER_QUEUE.clear()


def test_health():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_provision_requires_auth():
    resp = client.post(
        "/api/v1/events/provision",
        json={"event_id": "e1", "tenant_id": "t1", "plan": "pro"},
    )
    assert resp.status_code == 401


def test_rbac_blocks_viewer_from_provisioning():
    token = _make_token(["VIEWER"])
    resp = client.post(
        "/api/v1/events/provision",
        headers={"Authorization": f"Bearer {token}"},
        json={"event_id": "e1", "tenant_id": "t1", "plan": "pro"},
    )
    assert resp.status_code == 403


def test_provision_and_fetch_tenant_config():
    op_token = _make_token(["OPERATOR"])
    resp = client.post(
        "/api/v1/events/provision",
        headers={"Authorization": f"Bearer {op_token}"},
        json={"event_id": "e1", "tenant_id": "acme", "plan": "enterprise", "region": "ap-south-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "PROVISIONED"

    viewer_token = _make_token(["VIEWER"])
    get_resp = client.get(
        "/api/v1/tenants/acme/config",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["plan"] == "enterprise"


def test_dlq_routing_and_admin_inspection():
    op_token = _make_token(["OPERATOR"])
    resp = client.post(
        "/api/v1/events/provision",
        headers={"Authorization": f"Bearer {op_token}"},
        json={
            "event_id": "e2",
            "tenant_id": "broken-tenant",
            "plan": "starter",
            "simulate_failure": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "DEAD_LETTERED"

    admin_token = _make_token(["ADMIN"])
    dlq_resp = client.get("/api/v1/dlq", headers={"Authorization": f"Bearer {admin_token}"})
    assert dlq_resp.status_code == 200
    assert dlq_resp.json()["count"] == 1
