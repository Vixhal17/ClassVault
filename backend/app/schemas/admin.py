import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateTeacherRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class TeacherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class AuditLogItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    ip: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime


class AuditLogPaginationResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[AuditLogItemResponse]
