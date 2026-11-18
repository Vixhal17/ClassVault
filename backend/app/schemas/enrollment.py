import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.enrollment import EnrollmentStatus


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    course_id: uuid.UUID
    course_name: Optional[str] = None
    course_code: Optional[str] = None
    status: EnrollmentStatus
    requested_at: datetime
    decided_at: Optional[datetime] = None


class EnrollmentDecisionRequest(BaseModel):
    status: EnrollmentStatus
