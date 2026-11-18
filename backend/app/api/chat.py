import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import get_redis, check_sliding_window_rate_limit
from app.models.user import User, UserRole
from app.models.chat import ChatMessage
from app.schemas.chat import ChatRequest, ChatMessageResponse, FeedbackRequest
from app.permissions import require_course_access, is_admin
from app.services.rag import execute_rag_query, execute_rag_streaming_query

settings = get_settings()

router = APIRouter(tags=["chat"])


@router.post("/courses/{course_id}/chat", response_model=ChatMessageResponse)
async def ask_course_chat(
    course_id: uuid.UUID,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Ask a question about the course material (non-streaming).
    Enforces 20 questions/hr/student rate limit.
    Enforces anti-IDOR course access.
    """
    # 1. Permission check
    course, enrollment = await require_course_access(course_id, current_user, db)

    # 2. Rate limit (applies to students)
    if current_user.role == UserRole.STUDENT:
        await check_sliding_window_rate_limit(
            redis=redis,
            key_prefix="chat",
            identifier=str(current_user.id),
            limit=settings.CHAT_LIMIT_PER_HOUR,
            window_seconds=3600,
        )

    # 3. Execute RAG
    msg = await execute_rag_query(
        db=db,
        redis=redis,
        course_id=course_id,
        user_id=current_user.id,
        question=req.question,
        unit_id=req.unit_id,
    )
    return msg


@router.post("/courses/{course_id}/chat/stream")
async def ask_course_chat_stream(
    course_id: uuid.UUID,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Ask a question about course material with Server-Sent Events (SSE) streaming.
    Streams sources first, then text tokens, then done event with message metadata.
    """
    # 1. Permission check
    course, enrollment = await require_course_access(course_id, current_user, db)

    # 2. Rate limit
    if current_user.role == UserRole.STUDENT:
        await check_sliding_window_rate_limit(
            redis=redis,
            key_prefix="chat",
            identifier=str(current_user.id),
            limit=settings.CHAT_LIMIT_PER_HOUR,
            window_seconds=3600,
        )

    # 3. Return StreamingResponse
    return StreamingResponse(
        execute_rag_streaming_query(
            db=db,
            redis=redis,
            course_id=course_id,
            user_id=current_user.id,
            question=req.question,
            unit_id=req.unit_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/courses/{course_id}/chat", response_model=List[ChatMessageResponse])
async def get_chat_history(
    course_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get chat history for the user in the course.
    """
    await require_course_access(course_id, current_user, db)

    stmt = (
        select(ChatMessage)
        .where(
            and_(
                ChatMessage.course_id == course_id,
                ChatMessage.user_id == current_user.id,
            )
        )
        .order_by(ChatMessage.created_at.asc())
        .limit(50)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/chat/{message_id}/feedback")
async def rate_chat_message(
    message_id: uuid.UUID,
    req: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rate an assistant answer (helpful / not_helpful).
    """
    stmt = select(ChatMessage).where(ChatMessage.id == message_id)
    result = await db.execute(stmt)
    msg = result.scalar_one_or_none()

    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

    if not is_admin(current_user) and msg.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

    msg.rating = req.rating
    await db.commit()
    return {"status": "ok", "rating": req.rating}
