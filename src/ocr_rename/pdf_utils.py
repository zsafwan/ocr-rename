import base64
import io
from pathlib import Path

import pymupdf

from .config import DEFAULT_MAX_PAGES, DEFAULT_MAX_PDF_SIZE_MB, FALLBACK_PAGES


def extract_first_pages(pdf_path: Path, max_pages: int = DEFAULT_MAX_PAGES,
                        max_size_mb: int = DEFAULT_MAX_PDF_SIZE_MB) -> bytes:
    """Extract first N pages from a PDF, falling back to fewer pages if too large."""
    src = pymupdf.open(str(pdf_path))
    total_pages = len(src)

    pages_to_try = [min(max_pages, total_pages)] + [
        min(p, total_pages) for p in FALLBACK_PAGES
    ]

    for num_pages in pages_to_try:
        pdf_bytes = _extract_pages(src, num_pages)
        size_mb = len(pdf_bytes) / (1024 * 1024)
        if size_mb <= max_size_mb:
            src.close()
            return pdf_bytes

    # Last resort: single page, return regardless of size
    src.close()
    return pdf_bytes


def _extract_pages(src: pymupdf.Document, num_pages: int) -> bytes:
    """Extract specified number of pages into a new PDF in memory."""
    dst = pymupdf.open()
    dst.insert_pdf(src, from_page=0, to_page=num_pages - 1)
    buf = io.BytesIO()
    dst.save(buf)
    dst.close()
    return buf.getvalue()


def pdf_to_base64(pdf_bytes: bytes) -> str:
    """Encode PDF bytes to base64 string."""
    return base64.standard_b64encode(pdf_bytes).decode("ascii")
