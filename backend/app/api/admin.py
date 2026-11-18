from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.deps import require_role
from app.core.rate_limit import get_client_ip
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.admin import CreateTeacherRequest, TeacherResponse
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
