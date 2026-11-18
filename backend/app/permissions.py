"""
Permissions and Access Control (Single Source of Truth)

All access checks must go through these functions.
Never trust course_id, user_id, or role sent by client.
"""

from typing import Any


def is_admin(user: Any) -> bool:
    return getattr(user, "role", None) == "admin"


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
    if user.role == "teacher":
        return course.teacher_id == user.id
    if user.role == "student":
        return enrollment is not None and enrollment.status == "approved"
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
    return user.role == "teacher" and course.teacher_id == user.id


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
    if user.role == "teacher":
        return file.uploaded_by == user.id or getattr(file, "course_teacher_id", None) == user.id
    if user.role == "student":
        return enrollment is not None and enrollment.status == "approved"
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
    if user.role == "teacher":
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
