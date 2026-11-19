"""Append reference PDFs to an exported PDF (Qt-free; needs `pip install pypdf`)."""
from __future__ import annotations
import io


def available():
    try:
        import pypdf  # noqa: F401
        return True
    except ImportError:
        return False


def append_pdfs(path, blobs):
    """Add the pages of each PDF (bytes) after the pages of the file at `path`.
    -> list of names/indexes that could not be read (empty when all went in). Raises ImportError without pypdf."""
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    w.append(PdfReader(path))
    bad = []
    for i, data in enumerate(blobs):
        try:
            w.append(PdfReader(io.BytesIO(data)))
        except Exception:                      # noqa: BLE001 - a damaged reference file must not lose the export
            bad.append(i)
    with open(path, "wb") as f:
        w.write(f)
    return bad
