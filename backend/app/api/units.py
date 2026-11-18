import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.models.unit import Unit
from app.permissions import require_course_access, require_course_manage, can_manage_course
from app.schemas.unit import UnitCreate, UnitUpdate, UnitResponse

router = APIRouter(tags=["Units"])


@router.post("/courses/{id}/units", response_model=UnitResponse, status_code=status.HTTP_201_CREATED)
async def create_unit(
    id: uuid.UUID,
    req: UnitCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_manage(id, current_user, db)

    unit = Unit(
        course_id=course.id,
        title=req.title.strip(),
        position=req.position or 0,
        is_published=True,
    )
    db.add(unit)
    await db.commit()
    await db.refresh(unit)

    return unit


@router.get("/courses/{id}/units", response_model=List[UnitResponse])
async def list_course_units(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course, _ = await require_course_access(id, current_user, db)

    stmt = select(Unit).where(Unit.course_id == course.id)

    # Students only see published units
    if current_user.role == UserRole.STUDENT:
        stmt = stmt.where(Unit.is_published.is_(True))

    stmt = stmt.order_by(Unit.position.asc(), Unit.created_at.asc())
    result = await db.execute(stmt)
    units = result.scalars().all()

    return units


@router.patch("/units/{id}", response_model=UnitResponse)
async def update_unit(
    id: uuid.UUID,
    req: UnitUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Unit).where(Unit.id == id)
    result = await db.execute(stmt)
    unit = result.scalar_one_or_none()

    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found.",
        )

    # Verify manage permissions for the parent course
    if not can_manage_course(current_user, unit.course):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found.",
        )

    if req.title is not None:
        unit.title = req.title.strip()
    if req.position is not None:
        unit.position = req.position
    if req.is_published is not None:
        unit.is_published = req.is_published

    await db.commit()
    await db.refresh(unit)

    return unit
