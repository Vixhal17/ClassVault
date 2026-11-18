import uuid
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field


class SourceCitation(BaseModel):
    file_id: str
    file_name: str
    page: int


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    unit_id: Optional[uuid.UUID] = None


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    user_id: uuid.UUID
    question: str
    answer: str
    sources: List[SourceCitation]
    rating: Optional[str] = None
    created_at: datetime


class FeedbackRequest(BaseModel):
    rating: Literal["helpful", "not_helpful"]
