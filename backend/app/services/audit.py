import uuid
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.core.logging import logger


async def log_audit(
    db: AsyncSession,
    action: str,
    user_id: Optional[uuid.UUID] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    ip: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
):
    """Record an audit trail event in PostgreSQL."""
    try:
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            ip=ip,
            metadata_=metadata,
        )
        db.add(log_entry)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log for action '{action}': {e}")
