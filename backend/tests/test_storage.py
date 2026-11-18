import pytest
from app.services.storage import FakeStorage

@pytest.mark.asyncio
async def test_fake_storage_crud():
    fake = FakeStorage()
    assert await fake.ping() is True

    # Put
    key = "courses/1/unit-1/test.pdf"
    content = b"%PDF-1.4 test pdf content"
    saved_key = await fake.put_pdf(key, content)
    assert saved_key == key

    # Get bytes
    retrieved = await fake.get_pdf_bytes(key)
    assert retrieved == content

    # Get stream
    chunks = []
    async for chunk in fake.get_pdf_stream(key):
        chunks.append(chunk)
    assert b"".join(chunks) == content

    # Presigned URL
    url = await fake.generate_presigned_download_url(key, expires_in=60)
    assert "download" in url
    assert key in url

    # Delete
    deleted = await fake.delete_pdf(key)
    assert deleted is True

    with pytest.raises(KeyError):
        await fake.get_pdf_bytes(key)
