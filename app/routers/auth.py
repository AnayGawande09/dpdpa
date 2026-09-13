from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

# Implemented in Phase 1: seeded demo admin, POST /auth/login, get_current_user dependency.
