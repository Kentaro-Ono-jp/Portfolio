from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from scripts.pdf_fixture import build_single_page_text_pdf

import reactorfront_ml.pdf_processing as pdf_processing
from reactorfront_ml.domain import PermanentProcessingError, ProcessingFailureCode
from reactorfront_ml.pdf_processing import extract_single_page_text


def blank_pdf(*, pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_extracts_text_from_supported_single_page_pdf() -> None:
    content = build_single_page_text_pdf(
        "REACTORFRONT SYNTHETIC INVOICE\nInvoice INV-9001\nTotal amount due 125.00"
    )

    text = extract_single_page_text(content)

    assert "Invoice INV-9001" in text
    assert "Total amount due 125.00" in text


def test_rejects_malformed_pdf() -> None:
    with pytest.raises(PermanentProcessingError) as raised:
        extract_single_page_text(b"%PDF-not-valid")
    assert raised.value.code is ProcessingFailureCode.INVALID_PDF


def test_rejects_multiple_pages() -> None:
    with pytest.raises(PermanentProcessingError) as raised:
        extract_single_page_text(blank_pdf(pages=2))
    assert raised.value.code is ProcessingFailureCode.PDF_PAGE_COUNT_UNSUPPORTED


def test_rejects_page_without_extractable_text() -> None:
    with pytest.raises(PermanentProcessingError) as raised:
        extract_single_page_text(blank_pdf(pages=1))
    assert raised.value.code is ProcessingFailureCode.PDF_TEXT_EXTRACTION_FAILED


def test_rejects_encrypted_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = type("EncryptedReader", (), {"is_encrypted": True})()
    monkeypatch.setattr(pdf_processing, "PdfReader", lambda *args, **kwargs: reader)

    with pytest.raises(PermanentProcessingError) as raised:
        extract_single_page_text(b"pdf")

    assert raised.value.code is ProcessingFailureCode.PDF_ENCRYPTED


def test_sanitizes_extraction_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenPage:
        @staticmethod
        def extract_text() -> str:
            raise ValueError("private parser detail")

    reader = type(
        "BrokenReader",
        (),
        {"is_encrypted": False, "pages": [BrokenPage()]},
    )()
    monkeypatch.setattr(pdf_processing, "PdfReader", lambda *args, **kwargs: reader)

    with pytest.raises(PermanentProcessingError) as raised:
        extract_single_page_text(b"pdf")

    assert raised.value.code is ProcessingFailureCode.PDF_TEXT_EXTRACTION_FAILED
