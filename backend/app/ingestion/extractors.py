"""Text extraction per format. Output keeps page numbers where the format has pages.

PDF  -> one PageText per page (page numbers power citations later)
DOCX -> one PageText (Word files have no fixed pages); paragraphs + tables
TXT  -> one PageText
CSV  -> one PageText; each row rendered as "column: value" pairs so it reads as prose
"""

import csv
import io
from dataclasses import dataclass
from pathlib import Path

import docx
import pymupdf

from app.ingestion import IngestionError
from app.ingestion.validation import decode_text
from app.models import DocumentFormat

MAX_CSV_ROWS = 50_000


@dataclass(frozen=True)
class PageText:
    page: int | None  # 1-based page number, or None when the format has no pages
    text: str


def extract_pdf(path: Path, max_pages: int) -> list[PageText]:
    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise IngestionError("The PDF could not be opened (corrupted file?).") from exc
    with document:
        if document.needs_pass:
            raise IngestionError("The PDF is password-protected.")
        if document.page_count > max_pages:
            raise IngestionError(f"The PDF has more than {max_pages} pages.")
        return [
            PageText(page=number, text=page.get_text("text"))
            for number, page in enumerate(document, start=1)
        ]


def extract_docx(path: Path) -> list[PageText]:
    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise IngestionError("The DOCX file could not be opened (corrupted file?).") from exc
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return [PageText(page=None, text="\n".join(parts))]


def _decode(path: Path) -> str:
    try:
        return decode_text(path.read_bytes())
    except ValueError as exc:
        raise IngestionError("The text file could not be decoded.") from exc


def extract_txt(path: Path) -> list[PageText]:
    return [PageText(page=None, text=_decode(path))]


def extract_csv(path: Path) -> list[PageText]:
    rows = csv.reader(io.StringIO(_decode(path)))
    header = next(rows, None)
    if not header:
        return [PageText(page=None, text="")]
    header = [column.strip() or f"column_{i + 1}" for i, column in enumerate(header)]

    lines = []
    for count, row in enumerate(rows, start=1):
        if count > MAX_CSV_ROWS:
            raise IngestionError(f"The CSV has more than {MAX_CSV_ROWS} rows.")
        pairs = [f"{col}: {val.strip()}" for col, val in zip(header, row, strict=False) if val]
        if pairs:
            lines.append("; ".join(pairs))
    return [PageText(page=None, text="\n".join(lines))]


def extract(path: Path, fmt: DocumentFormat, *, max_pdf_pages: int = 500) -> list[PageText]:
    if fmt is DocumentFormat.PDF:
        return extract_pdf(path, max_pdf_pages)
    if fmt is DocumentFormat.DOCX:
        return extract_docx(path)
    if fmt is DocumentFormat.CSV:
        return extract_csv(path)
    return extract_txt(path)
