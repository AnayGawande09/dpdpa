# DEMO AUTH ONLY — replace with real IAM before production.
import asyncio

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.user import User
from app.security import hash_password

DEMO_ADMIN_EMAIL = "admin@example.com"
DEMO_ADMIN_PASSWORD = "DemoPass123!"


async def seed_demo_admin() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == DEMO_ADMIN_EMAIL))
        if result.scalar_one_or_none() is not None:
            return
        user = User(
            email=DEMO_ADMIN_EMAIL,
            hashed_password=hash_password(DEMO_ADMIN_PASSWORD),
            role="admin",
        )
        db.add(user)
        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed_demo_admin())
