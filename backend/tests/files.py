"""Helpers that generate real PDF / DOCX / CSV / TXT files for tests."""

from pathlib import Path

import docx
import pymupdf


def make_pdf(path: Path, pages: list[str]) -> Path:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    document.save(path)
    document.close()
    return path


def make_docx(path: Path, paragraphs: list[str], table: list[list[str]] | None = None) -> Path:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                grid.cell(r, c).text = value
    document.save(path)
    return path


def pdf_bytes(pages: list[str], tmp_path: Path) -> bytes:
    return make_pdf(tmp_path / "generated.pdf", pages).read_bytes()


def docx_bytes(paragraphs: list[str], tmp_path: Path) -> bytes:
    return make_docx(tmp_path / "generated.docx", paragraphs).read_bytes()
