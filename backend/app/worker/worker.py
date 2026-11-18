from arq.connections import RedisSettings
from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

async def startup(ctx):
    logger.info("ClassVault ARQ background worker started.")

async def shutdown(ctx):
    logger.info("ClassVault ARQ background worker shutdown.")

async def process_pdf(ctx, file_id: str):
    logger.info(f"Worker received process_pdf for file_id: {file_id}")
    return {"file_id": file_id, "status": "processed"}

async def delete_file_vectors(ctx, file_id: str):
    logger.info(f"Worker received delete_file_vectors for file_id: {file_id}")
    return {"file_id": file_id, "status": "deleted"}

class WorkerSettings:
    functions = [process_pdf, delete_file_vectors]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
