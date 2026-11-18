import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.core.database import get_db
from app.core.deps import require_role
from app.core.rate_limit import get_client_ip
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.audit import AuditLog
from app.schemas.admin import (
    CreateTeacherRequest,
    TeacherResponse,
    AuditLogItemResponse,
    AuditLogPaginationResponse,
)
from app.services.audit import log_audit

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/teachers", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    req: CreateTeacherRequest,
    request: Request,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    email = req.email.strip().lower()

    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    teacher = User(
        name=req.name.strip(),
        email=email,
        password_hash=hash_password(req.password),
        role=UserRole.TEACHER,
        is_active=True,
    )
    db.add(teacher)
    await db.commit()
    await db.refresh(teacher)

    ip = get_client_ip(request)
    await log_audit(
        db=db,
        user_id=current_user.id,
        action="create_teacher",
        target_type="user",
        target_id=str(teacher.id),
        ip=ip,
        metadata={"created_email": teacher.email},
    )

    return teacher


@router.get("/audit-logs", response_model=AuditLogPaginationResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    action: Optional[str] = Query(None),
    user_id: Optional[uuid.UUID] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """
    Query system audit logs with pagination and filters.
    Restricted to system administrators.
    """
    query = select(AuditLog, User.email, User.role).outerjoin(User, AuditLog.user_id == User.id)
    count_query = select(func.count(AuditLog.id)).outerjoin(User, AuditLog.user_id == User.id)

    filters = []
    if action:
        filters.append(AuditLog.action.ilike(f"%{action.strip()}%"))
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if search:
        s = f"%{search.strip()}%"
        filters.append(
            or_(
                AuditLog.action.ilike(s),
                AuditLog.target_id.ilike(s),
                AuditLog.target_type.ilike(s),
                User.email.ilike(s),
                User.name.ilike(s),
            )
        )
    if start_date:
        filters.append(AuditLog.created_at >= start_date)
    if end_date:
        filters.append(AuditLog.created_at <= end_date)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)

    rows = (await db.execute(query)).all()

    items = []
    for audit_log, user_email, user_role in rows:
        items.append(
            AuditLogItemResponse(
                id=audit_log.id,
                user_id=audit_log.user_id,
                user_email=user_email,
                user_role=user_role.value if hasattr(user_role, "value") else user_role,
                action=audit_log.action,
                target_type=audit_log.target_type,
                target_id=audit_log.target_id,
                ip=audit_log.ip,
                metadata=audit_log.metadata_,
                created_at=audit_log.created_at,
            )
        )

    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1

    return AuditLogPaginationResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )
