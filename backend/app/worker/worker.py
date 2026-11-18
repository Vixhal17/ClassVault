import asyncio
from datetime import datetime, timezone, timedelta
import uuid
from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select, and_

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.models.file import File, FileStatus
from app.services.pdf_parser import extract_and_chunk_pdf, PermanentPdfError, TransientPdfError
from app.services.storage import get_storage
from app.services.vector_store import get_vector_store

settings = get_settings()


async def startup(ctx):
    logger.info("ClassVault ARQ background worker started.")
    # Initialize vector store collection
    vstore = get_vector_store()
    try:
        await vstore.ensure_collection()
    except Exception as e:
        logger.warning(f"Could not connect to vector store on startup: {e}")


async def shutdown(ctx):
    logger.info("ClassVault ARQ background worker shutdown.")


async def process_pdf(ctx, file_id: str):
    logger.info(f"Processing PDF for file_id: {file_id}")
    file_uuid = uuid.UUID(file_id)

    # 1. Fetch file record from DB
    async with AsyncSessionLocal() as session:
        stmt = select(File).where(File.id == file_uuid)
        result = await session.execute(stmt)
        file_rec = result.scalar_one_or_none()

        if not file_rec:
            logger.warning(f"File {file_id} not found in database.")
            return {"file_id": file_id, "status": "not_found"}

        if file_rec.deleted_at is not None:
            logger.info(f"File {file_id} is deleted. Aborting processing.")
            return {"file_id": file_id, "status": "aborted_deleted"}

        # Mark as processing
        file_rec.status = FileStatus.PROCESSING
        file_rec.error_msg = None
        await session.commit()

        course_id = str(file_rec.course_id)
        unit_id = str(file_rec.unit_id)
        storage_key = file_rec.storage_key
        original_name = file_rec.original_name

    # 2. Download PDF bytes
    storage = get_storage()
    try:
        pdf_bytes = await storage.get_pdf_bytes(storage_key)
    except Exception as e:
        logger.error(f"Failed to retrieve PDF bytes for {file_id}: {e}")
        job_try = ctx.get("job_try", 1)
        if job_try < 3:
            raise Retry(defer=job_try * 5)

        async with AsyncSessionLocal() as session:
            stmt = select(File).where(File.id == file_uuid)
            result = await session.execute(stmt)
            file_rec = result.scalar_one_or_none()
            if file_rec:
                file_rec.status = FileStatus.FAILED
                file_rec.error_msg = "Storage error: could not retrieve uploaded file."
                await session.commit()
        return {"file_id": file_id, "status": "failed", "error": "Storage error"}

    # 3. Extract text and chunk
    try:
        page_count, chunks = extract_and_chunk_pdf(
            pdf_bytes=pdf_bytes,
            course_id=course_id,
            unit_id=unit_id,
            file_id=file_id,
            file_name=original_name,
        )
    except PermanentPdfError as e:
        logger.warning(f"Permanent error processing PDF {file_id}: {e}")
        async with AsyncSessionLocal() as session:
            stmt = select(File).where(File.id == file_uuid)
            result = await session.execute(stmt)
            file_rec = result.scalar_one_or_none()
            if file_rec:
                file_rec.status = FileStatus.FAILED
                file_rec.error_msg = str(e)
                await session.commit()
        return {"file_id": file_id, "status": "failed", "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error processing PDF {file_id}: {e}")
        job_try = ctx.get("job_try", 1)
        if job_try < 3:
            raise Retry(defer=job_try * 5)

        async with AsyncSessionLocal() as session:
            stmt = select(File).where(File.id == file_uuid)
            result = await session.execute(stmt)
            file_rec = result.scalar_one_or_none()
            if file_rec:
                file_rec.status = FileStatus.FAILED
                file_rec.error_msg = f"Processing error: {str(e)}"
                await session.commit()
        return {"file_id": file_id, "status": "failed", "error": str(e)}

    # 4. Upsert vectors into Qdrant
    vstore = get_vector_store()
    try:
        await vstore.upsert_chunks(
            course_id=course_id,
            unit_id=unit_id,
            file_id=file_id,
            file_name=original_name,
            chunks=chunks,
        )
    except Exception as e:
        logger.error(f"Vector store upsert failed for {file_id}: {e}")
        job_try = ctx.get("job_try", 1)
        if job_try < 3:
            raise Retry(defer=job_try * 5)

        async with AsyncSessionLocal() as session:
            stmt = select(File).where(File.id == file_uuid)
            result = await session.execute(stmt)
            file_rec = result.scalar_one_or_none()
            if file_rec:
                file_rec.status = FileStatus.FAILED
                file_rec.error_msg = "Vector indexing failed."
                await session.commit()
        return {"file_id": file_id, "status": "failed", "error": "Vector indexing failed"}

    # 5. Final consistency re-check before marking ready
    async with AsyncSessionLocal() as session:
        stmt = select(File).where(File.id == file_uuid)
        result = await session.execute(stmt)
        file_rec = result.scalar_one_or_none()

        if not file_rec:
            await vstore.delete_file_chunks(file_id)
            return {"file_id": file_id, "status": "aborted_removed"}

        if file_rec.deleted_at is not None:
            logger.info(f"File {file_id} was deleted during processing. Deleting vectors.")
            await vstore.delete_file_chunks(file_id)
            return {"file_id": file_id, "status": "aborted_deleted"}

        file_rec.status = FileStatus.READY
        file_rec.page_count = page_count
        file_rec.error_msg = None
        await session.commit()

    # 6. Bump course_version counter in Redis to invalidate RAG cache
    redis = ctx.get("redis")
    if redis:
        try:
            await redis.incr(f"course_version:{course_id}")
        except Exception as e:
            logger.warning(f"Could not bump course_version for {course_id}: {e}")

    logger.info(f"File {file_id} successfully processed with {page_count} pages and {len(chunks)} chunks.")
    return {"file_id": file_id, "status": "ready", "pages": page_count, "chunks": len(chunks)}


async def delete_file_vectors(ctx, file_id: str):
    logger.info(f"Worker deleting vectors for file_id: {file_id}")
    vstore = get_vector_store()
    try:
        await vstore.delete_file_chunks(file_id)
    except Exception as e:
        logger.error(f"Failed to delete file vectors for {file_id}: {e}")
    return {"file_id": file_id, "status": "deleted"}


async def cleanup_stale_processing_jobs(ctx):
    """5-minute cron: find files stuck in 'processing' for > 10 minutes and re-queue them."""
    ten_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with AsyncSessionLocal() as session:
        stmt = select(File).where(
            and_(
                File.status == FileStatus.PROCESSING,
                File.created_at < ten_mins_ago,
                File.deleted_at.is_(None),
            )
        )
        result = await session.execute(stmt)
        stale_files = result.scalars().all()

        redis = ctx.get("redis")
        for f in stale_files:
            logger.warning(f"Re-queuing stale file {f.id} stuck in processing.")
            f.status = FileStatus.QUEUED
            await session.commit()
            if redis:
                await redis.enqueue_job("process_pdf", str(f.id), _job_id=f"pdf:{f.id}")


async def purge_old_deleted_files(ctx):
    """Daily cron: permanently purge files soft-deleted > 30 days ago from storage."""
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    async with AsyncSessionLocal() as session:
        stmt = select(File).where(
            and_(
                File.deleted_at.is_not(None),
                File.deleted_at < thirty_days_ago,
            )
        )
        result = await session.execute(stmt)
        expired_files = result.scalars().all()

        storage = get_storage()
        for f in expired_files:
            try:
                await storage.delete_pdf(f.storage_key)
                await session.delete(f)
                await session.commit()
                logger.info(f"Purged expired file {f.id} ({f.original_name}) from storage and database.")
            except Exception as e:
                logger.error(f"Failed to purge expired file {f.id}: {e}")


class WorkerSettings:
    functions = [process_pdf, delete_file_vectors]
    cron_jobs = [
        cron(cleanup_stale_processing_jobs, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(purge_old_deleted_files, hour=3, minute=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
