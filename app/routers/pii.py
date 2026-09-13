from fastapi import APIRouter

router = APIRouter(prefix="/datasets", tags=["pii"])

# Implemented in Phase 2: GET /datasets/{scan_id}/pii (masked, grouped by field).
