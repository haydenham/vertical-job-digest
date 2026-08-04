"""Unit tests for the résumé ingestion adapter (`vja.resume`, P9.3 / D-057).

Pins the upload-boundary `bytes → resume_text` contract: text/markdown decode, text-PDF
extraction, and every rejection mode (scanned/empty PDF, non-text bytes, empty, oversize) mapping
to a `ResumeError`. PDFs are built at test time with correct xref offsets (no fixtures, no dep).
Update 1.2 adds `clean_resume_text`, the paste path's entry point, pinned against the upload
path's tail so the two cannot drift.
"""

import pytest

from vja.resume import (
    _MAX_BYTES,
    _MAX_CHARS,
    ResumeError,
    clean_resume_text,
    extract_resume_text,
)


def _make_pdf(text: str) -> bytes:
    """A minimal one-page PDF whose text operator renders `text` (with a correct xref table)."""
    stream = b"BT /F1 24 Tf 72 700 Td (" + text.encode("latin-1") + b") Tj ET"
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj" + body + b"endobj\n"
    xref_pos = len(out)
    n = len(objs) + 1
    out += b"xref\n0 " + str(n).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer<</Size " + str(n).encode() + b"/Root 1 0 R>>\nstartxref\n"
    out += str(xref_pos).encode() + b"\n%%EOF"
    return bytes(out)


def test_plain_text_passes_through() -> None:
    assert extract_resume_text("resume.txt", b"  Jane Engineer\nPython, Go  ") == (
        "Jane Engineer\nPython, Go"
    )


def test_markdown_is_just_text() -> None:
    md = b"# Jane\n\n- Python\n- Grid software"
    assert extract_resume_text("resume.md", md) == md.decode("utf-8")


def test_pdf_text_extraction() -> None:
    out = extract_resume_text("resume.pdf", _make_pdf("Hello Resume"))
    assert "Hello Resume" in out


def test_pdf_routed_by_magic_bytes_without_extension() -> None:
    # No .pdf extension — content sniffing (%PDF-) must still route to the PDF path.
    out = extract_resume_text("upload.bin", _make_pdf("Sniffed PDF"))
    assert "Sniffed PDF" in out


def test_scanned_or_textless_pdf_raises() -> None:
    with pytest.raises(ResumeError, match="scanned"):
        extract_resume_text("scan.pdf", _make_pdf(""))


def test_unreadable_pdf_raises() -> None:
    with pytest.raises(ResumeError, match="could not read PDF"):
        extract_resume_text("broken.pdf", b"%PDF-1.4 not really a pdf")


def test_non_utf8_text_raises() -> None:
    with pytest.raises(ResumeError, match="not UTF-8"):
        extract_resume_text("resume.txt", b"\xff\xfe\x00garbage")


def test_empty_upload_raises() -> None:
    with pytest.raises(ResumeError, match="empty"):
        extract_resume_text("resume.txt", b"")


def test_whitespace_only_raises() -> None:
    with pytest.raises(ResumeError, match="no extractable text"):
        extract_resume_text("resume.txt", b"   \n\t  ")


def test_oversize_bytes_raise() -> None:
    with pytest.raises(ResumeError, match="too large"):
        extract_resume_text("resume.txt", b"x" * (_MAX_BYTES + 1))


def test_too_long_text_raises() -> None:
    with pytest.raises(ResumeError, match="too long"):
        extract_resume_text("resume.txt", b"a" * (_MAX_CHARS + 1))


# --- the paste path (Update 1.2) --------------------------------------------------------------
# `clean_resume_text` is the already-text sibling. It must share the upload path's tail exactly:
# same strip, same emptiness rejection, same character cap. Its whole reason for existing is that
# the API does not get to re-implement those rules.


def test_pasted_text_is_stripped_and_returned() -> None:
    assert clean_resume_text("  Jane Engineer\nPython, Go  ") == "Jane Engineer\nPython, Go"


def test_pasted_text_matches_the_uploaded_text_exactly() -> None:
    """Same characters in, same text out — so `resume_version` and therefore every guard keyed on
    it (D-085's identical-content no-op, the rolling clock) cannot tell the two paths apart."""
    body = "  Jane Engineer. Python, grid software.\n"
    assert clean_resume_text(body) == extract_resume_text("resume.txt", body.encode())


def test_pasted_empty_raises() -> None:
    with pytest.raises(ResumeError, match="no résumé text"):
        clean_resume_text("")


def test_pasted_whitespace_only_raises() -> None:
    with pytest.raises(ResumeError, match="no résumé text"):
        clean_resume_text("   \n\t  ")


def test_pasted_too_long_raises() -> None:
    with pytest.raises(ResumeError, match="too long"):
        clean_resume_text("a" * (_MAX_CHARS + 1))


def test_pasted_at_the_cap_is_accepted() -> None:
    """The boundary is inclusive on both paths."""
    assert len(clean_resume_text("a" * _MAX_CHARS)) == _MAX_CHARS
