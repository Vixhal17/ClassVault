import re
import secrets
import string
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.user import User, UserRole
from app.models.course import Course
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.permissions import (
    require_course_access,
    require_course_manage,
    can_manage_course,
)
from app.schemas.course import CourseCreate, CourseUpdate, CourseResponse

router = APIRouter(prefix="/courses", tags=["Courses"])


def generate_join_code(course_code: str) -> str:
    """Generate unique readable join code like CS401-X7K2."""
    clean_prefix = re.sub(r"[^A-Za-z0-9]", "", course_code).upper()[:6] or "CV"
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(4))
    return f"{clean_prefix}-{suffix}"


async def get_unique_join_code(db: AsyncSession, course_code: str) -> str:
    for _ in range(10):
        code = generate_join_code(course_code)
        stmt = select(Course.id).where(Course.join_code == code)
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            return code
    # Fallback to random hex
    return f"CV-{secrets.token_hex(4).upper()}"


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    req: CourseCreate,
    current_user: User = Depends(require_role(UserRole.TEACHER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    join_code = await get_unique_join_code(db, req.code)

    course = Course(
        name=req.name.strip(),
        code=req.code.strip().upper(),
        teacher_id=current_user.id,
        join_code=join_code,
        join_enabled=True,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)

    return CourseResponse(
        id=course.id,
        name=course.name,
        code=course.code,
        teacher_id=course.teacher_id,
        teacher_name=current_user.name,
        join_code=course.join_code,
        join_enabled=course.join_enabled,
        created_at=course.created_at,
        student_count=0,
        pending_count=0,
    )


@router.get("", response_model=List[CourseResponse])
async def list_courses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Teachers: returns courses owned.
    Students: returns courses where enrollment is 'approved'.
    Admin: returns all courses.
    """
    courses_with_counts = []

    if current_user.role == UserRole.ADMIN:
        stmt = select(Course)
    elif current_user.role == UserRole.TEACHER:
        stmt = select(Course).where(Course.teacher_id == current_user.id)
    else:
        # Student: only approved enrollments
        stmt = (
            select(Course)
            .join(Enrollment, Course.id == Enrollment.course_id)
            .where(
                Enrollment.student_id == current_user.id,
                Enrollment.status == EnrollmentStatus.APPROVED,
            )
        )

    result = await db.execute(stmt)
    courses = result.scalars().all()

    for course in courses:
        # Compute approved student count
        stmt_approved = select(func.count(Enrollment.id)).where(
            Enrollment.course_id == course.id,
            Enrollment.status == EnrollmentStatus.APPROVED,
        )
        approved_count = (await db.execute(stmt_approved)).scalar() or 0

        # Compute pending request count (for teachers/admin)
        pending_count = 0
        if can_manage_course(current_user, course):
            stmt_pending = select(func.count(Enrollment.id)).where(
                Enrollment.course_id == course.id,
                Enrollment.status == EnrollmentStatus.PENDING,
            )
            pending_count = (await db.execute(stmt_pending)).scalar() or 0

        # Redact join_code for students
        join_code_display = course.join_code if can_manage_course(current_user, course) else None

        teacher_name = course.teacher.name if course.teacher else None

        courses_with_counts.append(
            CourseResponse(
                id=course.id,
                name=course.name,
                code=course.code,
                teacher_id=course.teacher_id,
                teacher_name=teacher_name,
                join_code=join_code_display,
                join_enabled=course.join_enabled,
                created_at=course.created_at,
                archived_at=course.archived_at,
                student_count=approved_count,
                pending_count=pending_count,
            )
        )

    return courses_with_counts


@router.get("/{id}", response_model=CourseResponse)
async def get_course(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course, _ = await require_course_access(id, current_user, db)

    # Approved count
    stmt_approved = select(func.count(Enrollment.id)).where(
        Enrollment.course_id == course.id,
        Enrollment.status == EnrollmentStatus.APPROVED,
    )
    approved_count = (await db.execute(stmt_approved)).scalar() or 0

    # Pending count
    pending_count = 0
    if can_manage_course(current_user, course):
        stmt_pending = select(func.count(Enrollment.id)).where(
            Enrollment.course_id == course.id,
            Enrollment.status == EnrollmentStatus.PENDING,
        )
        pending_count = (await db.execute(stmt_pending)).scalar() or 0

    join_code_display = course.join_code if can_manage_course(current_user, course) else None
    teacher_name = course.teacher.name if course.teacher else None

    return CourseResponse(
        id=course.id,
        name=course.name,
        code=course.code,
        teacher_id=course.teacher_id,
        teacher_name=teacher_name,
        join_code=join_code_display,
        join_enabled=course.join_enabled,
        created_at=course.created_at,
        archived_at=course.archived_at,
        student_count=approved_count,
        pending_count=pending_count,
    )


@router.patch("/{id}", response_model=CourseResponse)
async def update_course(
    id: uuid.UUID,
    req: CourseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_manage(id, current_user, db)

    if req.name is not None:
        course.name = req.name.strip()
    if req.code is not None:
        course.code = req.code.strip().upper()
    if req.join_enabled is not None:
        course.join_enabled = req.join_enabled

    await db.commit()
    await db.refresh(course)

    return await get_course(id=course.id, current_user=current_user, db=db)


@router.post("/{id}/rotate-code", response_model=CourseResponse)
async def rotate_join_code(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await require_course_manage(id, current_user, db)
    new_code = await get_unique_join_code(db, course.code)
    course.join_code = new_code
    await db.commit()
    await db.refresh(course)

    return await get_course(id=course.id, current_user=current_user, db=db)


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_course(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a course.
    Teachers can delete courses they own; Admins can delete any course.
    Cascades to units, files, enrollments, and chat messages.
    """
    course = await require_course_manage(id, current_user, db)
    course_name = course.name
    await db.delete(course)
    await db.commit()
    return {"success": True, "message": f"Course '{course_name}' deleted."}
