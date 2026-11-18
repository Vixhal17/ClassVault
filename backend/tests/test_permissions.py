from types import SimpleNamespace
from app.permissions import (
    can_view_course,
    can_manage_course,
    can_upload_to_course,
    can_download_file,
    can_delete_file,
    can_chat_in_course,
)

def test_permissions_matrix():
    admin = SimpleNamespace(id="u1", role="admin", is_active=True)
    teacher1 = SimpleNamespace(id="u2", role="teacher", is_active=True)
    teacher2 = SimpleNamespace(id="u3", role="teacher", is_active=True)
    student_approved = SimpleNamespace(id="u4", role="student", is_active=True)
    student_pending = SimpleNamespace(id="u5", role="student", is_active=True)
    inactive_user = SimpleNamespace(id="u6", role="student", is_active=False)

    course = SimpleNamespace(id="c1", teacher_id="u2")
    enrollment_approved = SimpleNamespace(student_id="u4", course_id="c1", status="approved")
    enrollment_pending = SimpleNamespace(student_id="u5", course_id="c1", status="pending")

    file_ready = SimpleNamespace(id="f1", uploaded_by="u2", status="ready", deleted_at=None)
    file_queued = SimpleNamespace(id="f2", uploaded_by="u2", status="queued", deleted_at=None)
    file_deleted = SimpleNamespace(id="f3", uploaded_by="u2", status="ready", deleted_at="2026-11-18")

    # Course View
    assert can_view_course(admin, course) is True
    assert can_view_course(teacher1, course) is True
    assert can_view_course(teacher2, course) is False  # Cannot view other teacher's course
    assert can_view_course(student_approved, course, enrollment_approved) is True
    assert can_view_course(student_pending, course, enrollment_pending) is False
    assert can_view_course(inactive_user, course, enrollment_approved) is False

    # Course Manage
    assert can_manage_course(admin, course) is True
    assert can_manage_course(teacher1, course) is True
    assert can_manage_course(teacher2, course) is False
    assert can_manage_course(student_approved, course) is False

    # Upload
    assert can_upload_to_course(teacher1, course) is True
    assert can_upload_to_course(student_approved, course) is False

    # Download
    assert can_download_file(teacher1, file_ready) is True
    assert can_download_file(student_approved, file_ready, enrollment_approved) is True
    assert can_download_file(student_pending, file_ready, enrollment_pending) is False
    assert can_download_file(student_approved, file_queued, enrollment_approved) is False  # not ready
    assert can_download_file(student_approved, file_deleted, enrollment_approved) is False  # deleted

    # Delete File
    assert can_delete_file(admin, file_ready, course) is True
    assert can_delete_file(teacher1, file_ready, course) is True
    assert can_delete_file(teacher2, file_ready, course) is False
    assert can_delete_file(student_approved, file_ready, course) is False
