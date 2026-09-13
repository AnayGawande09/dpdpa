import pytest

from app.seed import DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD


@pytest.mark.asyncio
async def test_login_success(client):
    res = await client.post(
        "/auth/login",
        data={"username": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_PASSWORD},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    res = await client.post(
        "/auth/login",
        data={"username": DEMO_ADMIN_EMAIL, "password": "wrong-password"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_token(client):
    res = await client.get("/datasets/some-id")
    assert res.status_code == 401
