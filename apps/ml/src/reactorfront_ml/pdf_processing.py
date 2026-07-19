from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from reactorfront_ml.domain import PermanentProcessingError, ProcessingFailureCode


def extract_single_page_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content), strict=True)
    except (PdfReadError, ValueError, TypeError) as error:
        raise PermanentProcessingError(code=ProcessingFailureCode.INVALID_PDF) from error

    if reader.is_encrypted:
        raise PermanentProcessingError(code=ProcessingFailureCode.PDF_ENCRYPTED)
    if len(reader.pages) != 1:
        raise PermanentProcessingError(code=ProcessingFailureCode.PDF_PAGE_COUNT_UNSUPPORTED)
    try:
        text = reader.pages[0].extract_text()
    except (PdfReadError, ValueError, TypeError) as error:
        raise PermanentProcessingError(
            code=ProcessingFailureCode.PDF_TEXT_EXTRACTION_FAILED
        ) from error
    if text is None or not text.strip():
        raise PermanentProcessingError(code=ProcessingFailureCode.PDF_TEXT_EXTRACTION_FAILED)
    return text
