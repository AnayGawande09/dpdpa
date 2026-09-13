from fastapi import APIRouter

router = APIRouter(prefix="/datasets", tags=["rules"])

# Implemented in Phase 5: GET /datasets/{scan_id}/rules.
