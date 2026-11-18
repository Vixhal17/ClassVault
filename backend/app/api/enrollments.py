from datetime import datetime, timezone
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.rate_limit import get_redis, check_sliding_window_rate_limit
from app.core.deps import get_current_user, require_role
from app.models.user import User, UserRole
from app.models.course import Course
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.permissions import require_course_manage, can_manage_course
from app.schemas.course import JoinCourseRequest
from app.schemas.enrollment import EnrollmentResponse, EnrollmentDecisionRequest
from app.services.audit import log_audit

router = APIRouter(tags=["Enrollments"])


@router.post("/courses/join", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def join_course(
    req: JoinCourseRequest,
    current_user: User = Depends(require_role(UserRole.STUDENT)),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    # Rate limit: 10 join requests per hour per user
    await check_sliding_window_rate_limit(
        redis=redis,
        key_prefix="join_course",
        identifier=str(current_user.id),
        limit=10,
        window_seconds=3600,
    )

    clean_code = req.code.strip().upper()

    # Find course by join code
    stmt = select(Course).where(Course.join_code == clean_code)
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid course join code.",
        )

    if not course.join_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Joining is currently disabled for this course.",
        )

    # Check for existing enrollment
    stmt_enroll = select(Enrollment).where(
        Enrollment.student_id == current_user.id,
        Enrollment.course_id == course.id,
    )
    res_enroll = await db.execute(stmt_enroll)
    enrollment = res_enroll.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if enrollment:
        if enrollment.status == EnrollmentStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already enrolled in this course.",
            )
        if enrollment.status == EnrollmentStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your join request is already pending approval.",
            )
        # Re-requesting after rejected or removed
        enrollment.status = EnrollmentStatus.PENDING
        enrollment.requested_at = now
        enrollment.decided_at = None
    else:
        enrollment = Enrollment(
            student_id=current_user.id,
            course_id=course.id,
            status=EnrollmentStatus.PENDING,
            requested_at=now,
        )
        db.add(enrollment)

    await db.commit()
    await db.refresh(enrollment)

    await log_audit(
        db=db,
        user_id=current_user.id,
        action="join_requested",
        target_type="course",
        target_id=str(course.id),
        metadata={"course_code": course.code, "enrollment_id": str(enrollment.id)},
    )

    return EnrollmentResponse(
        id=enrollment.id,
        student_id=current_user.id,
        student_name=current_user.name,
        student_email=current_user.email,
        course_id=course.id,
        course_name=course.name,
        course_code=course.code,
        status=enrollment.status,
        requested_at=enrollment.requested_at,
        decided_at=enrollment.decided_at,
    )


@router.get("/courses/{id}/requests", response_model=List[EnrollmentResponse])
async def list_course_requests(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_manage(id, current_user, db)

    stmt = (
        select(Enrollment)
        .where(
            Enrollment.course_id == course.id,
            Enrollment.status == EnrollmentStatus.PENDING,
        )
        .order_by(Enrollment.requested_at.asc())
    )
    result = await db.execute(stmt)
    enrollments = result.scalars().all()

    return [
        EnrollmentResponse(
            id=e.id,
            student_id=e.student_id,
            student_name=e.student.name if e.student else None,
            student_email=e.student.email if e.student else None,
            course_id=course.id,
            course_name=course.name,
            course_code=course.code,
            status=e.status,
            requested_at=e.requested_at,
            decided_at=e.decided_at,
        )
        for e in enrollments
    ]


@router.get("/courses/{id}/students", response_model=List[EnrollmentResponse])
async def list_course_students(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_manage(id, current_user, db)

    stmt = (
        select(Enrollment)
        .where(
            Enrollment.course_id == course.id,
            Enrollment.status == EnrollmentStatus.APPROVED,
        )
        .order_by(Enrollment.decided_at.desc())
    )
    result = await db.execute(stmt)
    enrollments = result.scalars().all()

    return [
        EnrollmentResponse(
            id=e.id,
            student_id=e.student_id,
            student_name=e.student.name if e.student else None,
            student_email=e.student.email if e.student else None,
            course_id=course.id,
            course_name=course.name,
            course_code=course.code,
            status=e.status,
            requested_at=e.requested_at,
            decided_at=e.decided_at,
        )
        for e in enrollments
    ]


@router.patch("/enrollments/{id}", response_model=EnrollmentResponse)
async def update_enrollment_status(
    id: uuid.UUID,
    req: EnrollmentDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Enrollment).where(Enrollment.id == id)
    result = await db.execute(stmt)
    enrollment = result.scalar_one_or_none()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found.",
        )

    # Check that current user can manage the course
    course = enrollment.course
    if not can_manage_course(current_user, course):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found.",
        )

    enrollment.status = req.status
    enrollment.decided_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(enrollment)

    await log_audit(
        db=db,
        user_id=current_user.id,
        action=f"enrollment_{req.status.value}",
        target_type="enrollment",
        target_id=str(enrollment.id),
        metadata={
            "student_id": str(enrollment.student_id),
            "course_id": str(enrollment.course_id),
            "new_status": req.status.value,
        },
    )

    return EnrollmentResponse(
        id=enrollment.id,
        student_id=enrollment.student_id,
        student_name=enrollment.student.name if enrollment.student else None,
        student_email=enrollment.student.email if enrollment.student else None,
        course_id=course.id,
        course_name=course.name,
        course_code=course.code,
        status=enrollment.status,
        requested_at=enrollment.requested_at,
        decided_at=enrollment.decided_at,
    )
