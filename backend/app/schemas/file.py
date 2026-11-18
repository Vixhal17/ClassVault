import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    unit_id: uuid.UUID
    course_id: uuid.UUID
    original_name: str
    size_bytes: int
    status: str
    error_msg: Optional[str] = None
    page_count: Optional[int] = None
    created_at: datetime
    deleted_at: Optional[datetime] = None


class FileUploadResponse(BaseModel):
    file_id: uuid.UUID
    status: str = "queued"


class PresignedDownloadResponse(BaseModel):
    download_url: str
    expires_in: int = 60
