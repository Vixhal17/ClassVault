import io
import os
from typing import AsyncGenerator, Optional
import aioboto3
from botocore.config import Config

from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()


class StorageService:
    def __init__(
        self,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        self.account_id = account_id or settings.R2_ACCOUNT_ID
        self.access_key_id = access_key_id or settings.R2_ACCESS_KEY_ID
        self.secret_access_key = secret_access_key or settings.R2_SECRET_ACCESS_KEY
        self.bucket_name = bucket_name or settings.R2_BUCKET
        self.session = aioboto3.Session()

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"

    @property
    def is_configured(self) -> bool:
        return bool(
            self.account_id
            and self.access_key_id
            and self.secret_access_key
            and not self.account_id.startswith("placeholder")
        )

    def _get_client_kwargs(self):
        return {
            "service_name": "s3",
            "endpoint_url": self.endpoint_url,
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
            "region_name": "auto",
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        }

    async def ping(self) -> bool:
        """Check R2 connectivity by checking bucket existence/head."""
        if not self.is_configured:
            logger.warning("Storage ping: Cloudflare R2 credentials not configured or using placeholders.")
            return False

        try:
            async with self.session.client(**self._get_client_kwargs()) as client:
                await client.head_bucket(Bucket=self.bucket_name)
                return True
        except Exception as e:
            logger.error(f"Storage ping failed for bucket {self.bucket_name}: {e}")
            return False

    async def put_pdf(self, storage_key: str, data: bytes) -> str:
        """Upload PDF bytes to private Cloudflare R2 bucket."""
        if not self.is_configured:
            raise RuntimeError("Cloudflare R2 is not configured.")

        async with self.session.client(**self._get_client_kwargs()) as client:
            await client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=data,
                ContentType="application/pdf",
            )
        return storage_key

    async def get_pdf_bytes(self, storage_key: str) -> bytes:
        """Retrieve full PDF bytes from R2."""
        if not self.is_configured:
            raise RuntimeError("Cloudflare R2 is not configured.")

        async with self.session.client(**self._get_client_kwargs()) as client:
            response = await client.get_object(Bucket=self.bucket_name, Key=storage_key)
            async with response["Body"] as stream:
                return await stream.read()

    async def get_pdf_stream(self, storage_key: str) -> AsyncGenerator[bytes, None]:
        """Stream PDF chunks from R2."""
        if not self.is_configured:
            raise RuntimeError("Cloudflare R2 is not configured.")

        async with self.session.client(**self._get_client_kwargs()) as client:
            response = await client.get_object(Bucket=self.bucket_name, Key=storage_key)
            async with response["Body"] as stream:
                while chunk := await stream.read(1024 * 1024):
                    yield chunk

    async def delete_pdf(self, storage_key: str) -> bool:
        """Permanently delete an object from R2."""
        if not self.is_configured:
            raise RuntimeError("Cloudflare R2 is not configured.")

        async with self.session.client(**self._get_client_kwargs()) as client:
            await client.delete_object(Bucket=self.bucket_name, Key=storage_key)
            return True

    async def generate_presigned_download_url(self, storage_key: str, expires_in: int = 60) -> str:
        """Generate a short-lived (default 60s) presigned download URL."""
        if not self.is_configured:
            raise RuntimeError("Cloudflare R2 is not configured.")

        async with self.session.client(**self._get_client_kwargs()) as client:
            url = await client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket_name, "Key": storage_key},
                ExpiresIn=expires_in,
            )
            return url


# In-memory and local filesystem fake storage for tests & local dev
class FakeStorage:
    def __init__(self, base_dir: Optional[str] = None):
        self.files: dict[str, bytes] = {}
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".local_storage")
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    async def ping(self) -> bool:
        return True

    def _file_path(self, storage_key: str) -> str:
        safe_key = storage_key.replace("/", os.sep).replace("\\", os.sep)
        return os.path.abspath(os.path.join(self.base_dir, safe_key))

    async def put_pdf(self, storage_key: str, data: bytes) -> str:
        self.files[storage_key] = data
        p = self._file_path(storage_key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return storage_key

    async def get_pdf_bytes(self, storage_key: str) -> bytes:
        if storage_key in self.files:
            return self.files[storage_key]
        p = self._file_path(storage_key)
        if os.path.exists(p):
            with open(p, "rb") as f:
                data = f.read()
                self.files[storage_key] = data
                return data
        raise KeyError(f"Key {storage_key} not found in FakeStorage")

    async def get_pdf_stream(self, storage_key: str) -> AsyncGenerator[bytes, None]:
        data = await self.get_pdf_bytes(storage_key)
        yield data

    async def delete_pdf(self, storage_key: str) -> bool:
        self.files.pop(storage_key, None)
        p = self._file_path(storage_key)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
        return True

    async def generate_presigned_download_url(self, storage_key: str, expires_in: int = 60) -> str:
        return f"https://fake-r2.local/download/{storage_key}?expires={expires_in}"


# Default singleton instance
storage = StorageService()

_fallback_fake_storage: Optional[FakeStorage] = None


def get_storage():
    """Returns Cloudflare R2 storage if configured, or in-memory FakeStorage for local dev/testing."""
    global _fallback_fake_storage
    if storage.is_configured:
        return storage
    if _fallback_fake_storage is None:
        _fallback_fake_storage = FakeStorage()
    return _fallback_fake_storage

