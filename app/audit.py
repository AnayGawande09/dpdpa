from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog


async def record_audit(
    db: AsyncSession,
    user_id: str,
    action: AuditAction,
    scan_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            scan_id=scan_id,
            action=action,
            details=details or {},
        )
    )
