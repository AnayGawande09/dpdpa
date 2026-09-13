from fastapi import APIRouter

router = APIRouter(prefix="/datasets", tags=["reports"])

# Implemented in Phase 8: POST/GET /datasets/{scan_id}/report, GET /audit-log.
