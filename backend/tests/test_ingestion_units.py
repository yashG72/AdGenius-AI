"""Unit tests for the ingestion steps: validation, extraction, cleaning, chunking."""

from pathlib import Path

import pytest

from app.core.exceptions import UnsupportedMediaTypeError
from app.ingestion import IngestionError
from app.ingestion.chunking import chunk_pages, count_tokens
from app.ingestion.cleaning import clean_text
from app.ingestion.extractors import PageText, extract
from app.ingestion.validation import format_from_filename, sanitize_filename, verify_content
from app.models import DocumentFormat
from tests.files import make_docx, make_pdf

# ---------- Validation ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\x\\Guide.PDF", "Guide.PDF"),
        ("bad\x00name\n.txt", "badname.txt"),
        ("", "untitled"),
    ],
)
def test_sanitize_filename(raw: str, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_format_from_filename() -> None:
    assert format_from_filename("Guide.PDF") is DocumentFormat.PDF
    with pytest.raises(UnsupportedMediaTypeError):
        format_from_filename("malware.exe")


def test_verify_content_rejects_renamed_files(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"MZ\x90\x00 this is an executable")
    with pytest.raises(UnsupportedMediaTypeError):
        verify_content(fake_pdf, DocumentFormat.PDF)

    binary_txt = tmp_path / "binary.txt"
    binary_txt.write_bytes(b"\x00\x01\x02binary")
    with pytest.raises(UnsupportedMediaTypeError):
        verify_content(binary_txt, DocumentFormat.TXT)

    zip_not_docx = tmp_path / "x.docx"
    zip_not_docx.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # empty zip archive
    with pytest.raises(UnsupportedMediaTypeError):
        verify_content(zip_not_docx, DocumentFormat.DOCX)


def test_verify_content_accepts_real_files(tmp_path: Path) -> None:
    verify_content(make_pdf(tmp_path / "a.pdf", ["hello"]), DocumentFormat.PDF)
    verify_content(make_docx(tmp_path / "a.docx", ["hello"]), DocumentFormat.DOCX)


# ---------- Extraction ----------


def test_extract_pdf_keeps_page_numbers(tmp_path: Path) -> None:
    path = make_pdf(tmp_path / "guide.pdf", ["Page one about colors.", "Page two about tone."])

    pages = extract(path, DocumentFormat.PDF)

    assert [p.page for p in pages] == [1, 2]
    assert "colors" in pages[0].text and "tone" in pages[1].text


def test_extract_pdf_page_limit(tmp_path: Path) -> None:
    path = make_pdf(tmp_path / "long.pdf", ["x"] * 3)

    with pytest.raises(IngestionError, match="more than 2 pages"):
        extract(path, DocumentFormat.PDF, max_pdf_pages=2)


def test_extract_docx_includes_tables(tmp_path: Path) -> None:
    path = make_docx(
        tmp_path / "spec.docx",
        ["MANO product specification"],
        table=[["Flavour", "Sugar"], ["Mango", "4g"]],
    )

    [page] = extract(path, DocumentFormat.DOCX)

    assert page.page is None
    assert "MANO product specification" in page.text
    assert "Mango | 4g" in page.text


def test_extract_csv_renders_rows_as_text(tmp_path: Path) -> None:
    path = tmp_path / "personas.csv"
    path.write_text("name,age,motto\nAsha,21,Stay curious\nRavi,,Keep going\n", encoding="utf-8")

    [page] = extract(path, DocumentFormat.CSV)

    assert page.text.splitlines() == [
        "name: Asha; age: 21; motto: Stay curious",
        "name: Ravi; motto: Keep going",
    ]


def test_extract_txt_handles_windows_encoding(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes("Café — crème".encode("cp1252"))

    [page] = extract(path, DocumentFormat.TXT)
    assert page.text == "Café — crème"


def test_corrupted_pdf_is_a_permanent_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7 garbage that is not a pdf")

    with pytest.raises(IngestionError):
        extract(path, DocumentFormat.PDF)


# ---------- Cleaning ----------


def test_clean_text() -> None:
    raw = "Brand  voice:\r\n\r\n\r\n\r\n\ufb01ne and adver-\ntising\x07 ready   \n"

    assert clean_text(raw) == "Brand voice:\n\nfine and advertising ready"


# ---------- Chunking ----------


def test_chunks_respect_size_overlap_and_pages() -> None:
    sentence = "The MANO brand voice is witty, youthful and confident. "
    pages = [PageText(1, sentence * 300), PageText(2, "Short second page."), PageText(3, "  ")]

    chunks = chunk_pages(pages, chunk_size=200, chunk_overlap=30)

    page_one = [c for c in chunks if c.page == 1]
    assert len(page_one) > 1
    # The splitter measures words separately, so joined chunks can exceed the target by
    # a token or two - fine, the embedding model accepts 8192 tokens.
    assert all(c.token_count <= 210 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))  # sequential
    assert chunks[-1].page == 2 and chunks[-1].text == "Short second page."  # empty page 3 skipped
    # Overlap: the start of chunk 2 repeats the end of chunk 1.
    assert page_one[1].text[:40] in page_one[0].text
    assert count_tokens("hello world") == 2
