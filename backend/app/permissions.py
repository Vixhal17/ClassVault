"""
Permissions and Access Control (Single Source of Truth)

All access checks must go through these functions.
Never trust course_id, user_id, or role sent by client.
Prevent IDOR: Return 404 (not 403) for resources the user should not know exist.
"""

import uuid
from typing import Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, UserRole
from app.models.course import Course
from app.models.enrollment import Enrollment, EnrollmentStatus


def is_admin(user: Any) -> bool:
    return getattr(user, "role", None) == UserRole.ADMIN or getattr(user, "role", None) == "admin"


def can_view_course(user: Any, course: Any, enrollment: Any = None) -> bool:
    """
    admin: can view any course.
    teacher: only if course.teacher_id == user.id.
    student: only if enrollment exists and enrollment.status == 'approved'.
    """
    if not user or not user.is_active:
        return False
    if is_admin(user):
        return True
    if user.role == UserRole.TEACHER or user.role == "teacher":
        return course.teacher_id == user.id
    if user.role == UserRole.STUDENT or user.role == "student":
        if enrollment is None:
            return False
        status_val = getattr(enrollment, "status", None)
        return status_val == EnrollmentStatus.APPROVED or status_val == "approved"
    return False


def can_manage_course(user: Any, course: Any) -> bool:
    """
    Course management (rename, archive, rotate code, approve/reject students, create units).
    admin or owner teacher.
    """
    if not user or not user.is_active:
        return False
    if is_admin(user):
        return True
    return (user.role == UserRole.TEACHER or user.role == "teacher") and course.teacher_id == user.id


def can_upload_to_course(user: Any, course: Any) -> bool:
    """
    Upload PDFs to course units.
    admin or owner teacher. Students can NEVER upload.
    """
    return can_manage_course(user, course)


def can_download_file(user: Any, file: Any, enrollment: Any = None) -> bool:
    """
    Download PDF file.
    - File must not be deleted.
    - File status must be 'ready'.
    - admin, owner teacher, or approved student.
    """
    if not user or not user.is_active:
        return False
    if getattr(file, "deleted_at", None) is not None:
        return False
    if getattr(file, "status", None) != "ready":
        return False

    if is_admin(user):
        return True
    if user.role == UserRole.TEACHER or user.role == "teacher":
        return file.uploaded_by == user.id or getattr(file, "course_teacher_id", None) == user.id
    if user.role == UserRole.STUDENT or user.role == "student":
        if enrollment is None:
            return False
        status_val = getattr(enrollment, "status", None)
        return status_val == EnrollmentStatus.APPROVED or status_val == "approved"
    return False


def can_delete_file(user: Any, file: Any, course: Any = None) -> bool:
    """
    Delete PDF file.
    admin or owner teacher. Students can NEVER delete.
    """
    if not user or not user.is_active:
        return False
    if is_admin(user):
        return True
    if user.role == UserRole.TEACHER or user.role == "teacher":
        if course:
            return course.teacher_id == user.id
        return file.uploaded_by == user.id
    return False


def can_chat_in_course(user: Any, course: Any, enrollment: Any = None) -> bool:
    """
    Ask questions in RAG chat.
    admin, owner teacher, or approved student.
    """
    return can_view_course(user, course, enrollment)


# Database-backed IDOR guards that raise 404
async def get_enrollment_for_user(
    db: AsyncSession, student_id: uuid.UUID, course_id: uuid.UUID
) -> Optional[Enrollment]:
    stmt = select(Enrollment).where(
        Enrollment.student_id == student_id,
        Enrollment.course_id == course_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def require_course_access(
    course_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> tuple[Course, Optional[Enrollment]]:
    """
    Load course and check can_view_course.
    Raises 404 if course does not exist OR if user does not have permission,
    preventing resource enumeration (IDOR).
    """
    stmt = select(Course).where(Course.id == course_id)
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )

    enrollment = None
    if user.role == UserRole.STUDENT:
        enrollment = await get_enrollment_for_user(db, user.id, course.id)

    if not can_view_course(user, course, enrollment):
        # 404 to avoid leaking course existence to unauthorized users
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )

    return course, enrollment


async def require_course_manage(
    course_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Course:
    """
    Load course and check can_manage_course.
    Raises 404 if user cannot manage course (preventing IDOR).
    """
    stmt = select(Course).where(Course.id == course_id)
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )

    if not can_manage_course(user, course):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )

    return course
