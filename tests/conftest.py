import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_dpdp.db"
os.environ["UPLOAD_DIR"] = "./test_uploads"
os.environ["MAX_UPLOAD_MB"] = "10"

import shutil

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, engine
from app.main import app
from app.seed import seed_demo_admin, DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD

TEST_DB_PATH = "./test_dpdp.db"
TEST_UPLOAD_DIR = "./test_uploads"


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_demo_admin()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except PermissionError:
            pass
    if os.path.exists(TEST_UPLOAD_DIR):
        shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token(client):
    res = await client.post(
        "/auth/login",
        data={"username": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_PASSWORD},
    )
    return res.json()["access_token"]
