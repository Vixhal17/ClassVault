import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.queue import get_arq_pool
from app.core.rate_limit import get_redis
from app.models.user import User, UserRole
from app.models.unit import Unit
from app.models.course import Course
from app.models.file import File, FileStatus
from app.services.audit import log_audit
from app.schemas.file import FileResponse, FileUploadResponse, PresignedDownloadResponse
from app.permissions import (
    require_course_manage,
    require_course_access,
    require_file_access,
    require_file_manage,
    is_admin,
)
from app.services.storage import get_storage
from app.services.vector_store import get_vector_store

router = APIRouter(tags=["files"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB limit


@router.post("/units/{unit_id}/files", response_model=FileUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    unit_id: uuid.UUID,
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a unit PDF.
    Validates MIME type, %PDF- magic bytes, and 20MB size limit.
    Streams to Cloudflare R2, records in DB as 'queued', enqueues ARQ job.
    Returns 202 Accepted.
    """
    # 1. Fetch unit and course
    stmt = select(Unit, Course).join(Course, Unit.course_id == Course.id).where(Unit.id == unit_id)
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found.")
    unit, course = row

    # 2. Permission check: teacher must own course or admin
    if not is_admin(current_user) and (current_user.role != UserRole.TEACHER or course.teacher_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found.")

    # 3. Read content and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of 20 MB (got {len(content) / (1024 * 1024):.1f} MB).",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 4. Validate MIME and magic bytes
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: expected application/pdf, received {file.content_type}.",
        )

    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PDF format: file lacks standard %PDF- header.",
        )

    # 5. Compute SHA256
    file_sha256 = hashlib.sha256(content).hexdigest()
    file_id = uuid.uuid4()
    sanitized_name = file.filename or f"unit_{unit_id}.pdf"
    storage_key = f"courses/{course.id}/units/{unit.id}/{file_id}.pdf"

    # 6. Upload to Cloudflare R2
    storage = get_storage()
    await storage.put_pdf(storage_key, content)

    # 7. Insert DB record
    file_record = File(
        id=file_id,
        unit_id=unit.id,
        course_id=course.id,
        uploaded_by=current_user.id,
        original_name=sanitized_name,
        storage_key=storage_key,
        size_bytes=len(content),
        sha256=file_sha256,
        status=FileStatus.QUEUED,
    )
    db.add(file_record)
    await db.commit()

    # 8. Audit log
    await log_audit(
        db=db,
        action="FILE_UPLOAD",
        user_id=current_user.id,
        target_type="file",
        target_id=str(file_id),
        metadata={"original_name": sanitized_name, "size_bytes": len(content), "course_id": str(course.id)},
    )

    # 9. Enqueue ARQ job
    try:
        arq_pool = await get_arq_pool()
        await arq_pool.enqueue_job("process_pdf", str(file_id), _job_id=f"pdf:{file_id}")
    except Exception as e:
        # Don't fail the upload request if queue worker is temporarily offline; file remains queued
        pass

    return FileUploadResponse(file_id=file_id, status="queued")


@router.get("/units/{unit_id}/files", response_model=List[FileResponse])
async def list_unit_files(
    unit_id: uuid.UUID,
    include_deleted: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List files for a unit.
    Students only receive 'ready' and non-deleted files.
    Teachers receive all active files (or deleted if include_deleted is true).
    """
    stmt = select(Unit, Course).join(Course, Unit.course_id == Course.id).where(Unit.id == unit_id)
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found.")
    unit, course = row

    if is_admin(current_user):
        pass
    elif current_user.role == UserRole.TEACHER:
        if course.teacher_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found.")
    else:
        # Student: verify course access and unpublished unit check
        if not unit.is_published:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found.")
        await require_course_access(course.id, current_user, db)

    # Build query
    query = select(File).where(File.unit_id == unit_id)

    if current_user.role == UserRole.STUDENT:
        # Enforce Section 4.3 rule in backend query
        query = query.where(and_(File.status == FileStatus.READY, File.deleted_at.is_(None)))
    else:
        if not include_deleted:
            query = query.where(File.deleted_at.is_(None))

    query = query.order_by(File.created_at.asc())
    files_result = await db.execute(query)
    return files_result.scalars().all()


@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file_status(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check processing status of a file.
    Students only see 'ready' files; others return 404.
    """
    file_rec, course = await require_file_access(file_id, current_user, db)
    return file_rec


@router.get("/files/{file_id}/download", response_model=PresignedDownloadResponse)
async def download_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a 60-second presigned URL for secure download.
    Never exposes permanent or public links.
    """
    file_rec, course = await require_file_access(file_id, current_user, db)

    storage = get_storage()
    download_url = await storage.generate_presigned_download_url(file_rec.storage_key, expires_in=60)

    # Audit log
    await log_audit(
        db=db,
        action="FILE_DOWNLOAD",
        user_id=current_user.id,
        target_type="file",
        target_id=str(file_rec.id),
        metadata={"file_name": file_rec.original_name, "course_id": str(course.id)},
    )

    return PresignedDownloadResponse(download_url=download_url, expires_in=60)


@router.post("/files/{file_id}/retry", response_model=FileResponse)
async def retry_file_processing(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Teacher action to retry failed file ingestion.
    """
    file_rec, course = await require_file_manage(file_id, current_user, db)

    file_rec.status = FileStatus.QUEUED
    file_rec.error_msg = None
    await db.commit()

    try:
        arq_pool = await get_arq_pool()
        job_key = f"pdf:{file_id}_{int(time.time())}"
        await arq_pool.enqueue_job("process_pdf", str(file_id), _job_id=job_key)
    except Exception:
        pass

    return file_rec


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Soft-delete file.
    Order matters:
    1. Delete file vectors from Qdrant immediately.
    2. Set deleted_at timestamp.
    3. Bump course_version counter in Redis.
    4. Write audit log.
    """
    file_rec, course = await require_file_manage(file_id, current_user, db)

    # 1. Delete vectors from Qdrant
    vstore = get_vector_store()
    await vstore.delete_file_chunks(str(file_id))

    # 2. Set deleted_at
    file_rec.deleted_at = datetime.now(timezone.utc)

    # 3. Bump course_version in Redis
    try:
        await redis.incr(f"course_version:{course.id}")
    except Exception:
        pass

    await db.commit()

    # 4. Audit log
    await log_audit(
        db=db,
        action="FILE_DELETE",
        user_id=current_user.id,
        target_type="file",
        target_id=str(file_rec.id),
        metadata={"file_name": file_rec.original_name, "course_id": str(course.id)},
    )

    return {"success": True, "message": "File deleted."}


@router.post("/files/{file_id}/restore", response_model=FileResponse)
async def restore_file(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Restore a soft-deleted file. Re-queues ingestion so vectors are regenerated.
    """
    file_rec, course = await require_file_manage(file_id, current_user, db)

    file_rec.deleted_at = None
    file_rec.status = FileStatus.QUEUED
    file_rec.error_msg = None
    await db.commit()

    # Re-queue ingestion
    try:
        arq_pool = await get_arq_pool()
        job_key = f"pdf:{file_id}_{int(time.time())}"
        await arq_pool.enqueue_job("process_pdf", str(file_id), _job_id=job_key)
    except Exception:
        pass

    # Audit log
    await log_audit(
        db=db,
        action="FILE_RESTORE",
        user_id=current_user.id,
        target_type="file",
        target_id=str(file_rec.id),
        metadata={"file_name": file_rec.original_name, "course_id": str(course.id)},
    )

    return file_rec
