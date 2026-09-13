from fastapi import APIRouter

router = APIRouter(prefix="/datasets", tags=["ingestion"])

# Implemented in Phase 1: POST /datasets/upload, GET /datasets/{scan_id},
# POST /datasets/{scan_id}/scan (stub).
