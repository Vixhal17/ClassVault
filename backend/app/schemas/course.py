import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=2, max_length=50)


class CourseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    join_enabled: Optional[bool] = None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    teacher_id: uuid.UUID
    teacher_name: Optional[str] = None
    join_code: Optional[str] = None  # Redacted for students
    join_enabled: bool
    created_at: datetime
    archived_at: Optional[datetime] = None
    student_count: int = 0
    pending_count: int = 0


class JoinCourseRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=30)
