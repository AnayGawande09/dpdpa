from fastapi import APIRouter

router = APIRouter(prefix="/datasets", tags=["findings"])

# Implemented in Phase 6: GET /datasets/{scan_id}/findings, GET /datasets/{scan_id}/risk.
