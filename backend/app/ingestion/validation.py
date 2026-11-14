"""Upload validation: file extension AND actual content must agree.

Trusting only the extension (or the browser's Content-Type) would let someone upload,
say, an executable renamed to .pdf. So we also check the file's leading "magic bytes".
"""

import unicodedata
import zipfile
from pathlib import Path, PurePath

from app.core.exceptions import UnsupportedMediaTypeError
from app.models import DocumentFormat

_EXTENSIONS = {f".{fmt.value}": fmt for fmt in DocumentFormat}
_MAX_DOCX_UNCOMPRESSED = 200 * 1024 * 1024  # zip-bomb guard


def sanitize_filename(filename: str | None) -> str:
    """Display-safe filename: no directories, no control characters, bounded length."""
    name = PurePath((filename or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    return name[-255:] or "untitled"


def format_from_filename(filename: str) -> DocumentFormat:
    fmt = _EXTENSIONS.get(PurePath(filename).suffix.lower())
    if fmt is None:
        allowed = ", ".join(sorted(_EXTENSIONS))
        raise UnsupportedMediaTypeError(f"Unsupported file type. Allowed: {allowed}.")
    return fmt


def decode_text(data: bytes) -> str:
    """Decode a text file (UTF-8 first, then Windows-1252). Raises ValueError if binary."""
    if b"\x00" in data:
        raise ValueError("binary content")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("unknown text encoding")


def verify_content(path: Path, fmt: DocumentFormat) -> None:
    """Raise UnsupportedMediaTypeError if the bytes don't match the claimed format."""
    mismatch = UnsupportedMediaTypeError(
        f"The file content is not a valid {fmt.value.upper()} file."
    )
    if fmt is DocumentFormat.PDF:
        with path.open("rb") as handle:
            if not handle.read(1024).lstrip().startswith(b"%PDF-"):
                raise mismatch
    elif fmt is DocumentFormat.DOCX:
        if not zipfile.is_zipfile(path):
            raise mismatch
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                raise mismatch
            if sum(info.file_size for info in archive.infolist()) > _MAX_DOCX_UNCOMPRESSED:
                raise UnsupportedMediaTypeError("The DOCX file expands to an unsafe size.")
    else:  # TXT / CSV
        try:
            decode_text(path.read_bytes())
        except ValueError as exc:
            raise mismatch from exc
