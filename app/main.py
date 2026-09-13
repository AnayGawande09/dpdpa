from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.routers import auth, findings, ingestion, pii, reports, rules
from app.seed import seed_demo_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_demo_admin()
    yield


app = FastAPI(title="DPDP Compliance Analyzer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ingestion.router)
app.include_router(pii.router)
app.include_router(rules.router)
app.include_router(findings.router)
app.include_router(reports.router)


@app.get("/health")
async def health():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        value = result.scalar_one()
    return {"status": "ok", "db_check": value}
