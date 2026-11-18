import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UnitCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    position: Optional[int] = 0


class UnitUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    position: Optional[int] = None
    is_published: Optional[bool] = None


class UnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    position: int
    is_published: bool
    created_at: datetime
