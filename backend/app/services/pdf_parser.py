import re
from typing import List, Tuple
import pymupdf

from app.services.vector_store import DocumentChunk


class PermanentPdfError(Exception):
    """Errors that should NOT be retried (corrupt, encrypted, empty/scanned)."""
    pass


class TransientPdfError(Exception):
    """Errors that can be retried (network glitches, timeouts)."""
    pass


def clean_text(text: str) -> str:
    """Normalize whitespace and remove non-printable characters."""
    if not text:
        return ""
    # Replace non-breaking spaces and tabs with standard space
    text = text.replace("\xa0", " ").replace("\t", " ")
    # Replace multiple spaces/newlines with single space/newline
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def chunk_page_text(text: str, chunk_size: int = 2000, overlap: int = 320) -> List[str]:
    """
    Split page text into chunks of ~500 tokens (~2000 characters)
    with ~80 tokens (~320 characters) overlap, breaking at paragraph or sentence boundaries.
    """
    text = clean_text(text)
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # Attempt to split at a clean boundary (paragraph or sentence)
        boundary = -1
        # Check for paragraph break in the last 400 chars of the window
        sub = text[start:end]
        para_idx = sub.rfind("\n\n")
        if para_idx > chunk_size // 2:
            boundary = start + para_idx + 2
        else:
            # Check for sentence end (.!?)
            sentence_match = list(re.finditer(r"[.!?]\s", sub))
            if sentence_match:
                last_sentence = sentence_match[-1]
                if last_sentence.end() > chunk_size // 2:
                    boundary = start + last_sentence.end()

        # If no sentence boundary found, split on space
        if boundary == -1:
            space_idx = sub.rfind(" ")
            if space_idx > chunk_size // 2:
                boundary = start + space_idx + 1
            else:
                boundary = end

        chunk = text[start:boundary].strip()
        if chunk:
            chunks.append(chunk)

        # Advance start with overlap
        start = max(boundary - overlap, start + 1)

    return chunks


def extract_and_chunk_pdf(
    pdf_bytes: bytes,
    course_id: str,
    unit_id: str,
    file_id: str,
    file_name: str,
    max_pages: int = 150,
) -> Tuple[int, List[DocumentChunk]]:
    """
    Extracts text from PDF, validates encryption and page limits,
    chunks text per page with page metadata preservation.
    """
    if not pdf_bytes:
        raise PermanentPdfError("Uploaded PDF file is empty (0 bytes).")

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise PermanentPdfError(f"Corrupt or unreadable PDF: {str(e)}")

    try:
        if doc.is_encrypted:
            raise PermanentPdfError("PDF is password-protected/encrypted and cannot be processed.")

        page_count = doc.page_count
        if page_count == 0:
            raise PermanentPdfError("PDF has 0 pages.")

        if page_count > max_pages:
            raise PermanentPdfError(
                f"PDF exceeds the maximum limit of {max_pages} pages (contains {page_count} pages)."
            )

        chunks: List[DocumentChunk] = []
        total_text_length = 0
        chunk_counter = 0

        for page_idx in range(page_count):
            page_num = page_idx + 1
            page = doc.load_page(page_idx)
            page_text = page.get_text("text") or ""
            cleaned = clean_text(page_text)
            total_text_length += len(cleaned)

            page_chunks = chunk_page_text(cleaned)
            for chunk_str in page_chunks:
                chunks.append(
                    DocumentChunk(
                        chunk_index=chunk_counter,
                        text=chunk_str,
                        page=page_num,
                        file_id=str(file_id),
                        file_name=file_name,
                        unit_id=str(unit_id),
                        course_id=str(course_id),
                    )
                )
                chunk_counter += 1

        if total_text_length < 20:
            raise PermanentPdfError(
                "PDF contains no extractable text (e.g. scanned image). Please upload an OCR-processed or text PDF."
            )

        return page_count, chunks

    finally:
        doc.close()
