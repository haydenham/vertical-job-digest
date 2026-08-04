"""Résumé ingestion adapter — the upload-boundary `bytes → resume_text` step (D-033).

Everything downstream of a profile reads `profiles.resume_text` (plain text), so the *input
format* is decoupled from matching/extraction (the D-033 seam). This module is that adapter and
nothing more: it turns an uploaded file into clean text, or rejects it. A **leaf** — it imports no
`vja` module, so it sits at the bottom of the import layering.

Scope (Phase 9.3, D-057): UTF-8 text/markdown and **text-based PDFs** (`pypdf`). A scanned/image PDF
has no extractable text layer → rejected (OCR / Claude native-PDF input is a later add). Update 1.2
adds the paste path: `clean_resume_text` is the sibling entry point for input that is *already* text
and needs no decoding, so the emptiness and length rules stay in one place instead of being
re-implemented at the API. All failure modes raise `ResumeError` so the API can map them to a 4xx.
**PII discipline (docs/11 §3.1): never log the text or the raw bytes.**
"""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

_PDF_MAGIC = b"%PDF-"
# Guardrails: a real résumé is small. These bound both abuse and accidental wrong-file uploads;
# the byte cap is also enforced (earlier, cheaply) at the API read boundary.
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB upload ceiling
_MAX_CHARS = 200_000  # ~50 pages of text — anything larger isn't a résumé


class ResumeError(ValueError):
    """An uploaded file could not be turned into usable résumé text (unsupported, empty, scanned,
    undecodable, or too large). The API maps it to a 4xx; the message is safe to surface."""


def extract_resume_text(filename: str | None, data: bytes) -> str:
    """Convert an uploaded résumé file to plain text, or raise `ResumeError`.

    Routing is by content, not trust: a `%PDF-` signature (or a `.pdf` name) goes through `pypdf`,
    everything else is decoded as UTF-8 text/markdown. A text-less (scanned) PDF, an undecodable
    blob, an empty result, or an oversized file all raise `ResumeError`.
    """
    if not data:
        raise ResumeError("empty upload")
    if len(data) > _MAX_BYTES:
        raise ResumeError(f"file too large ({len(data)} bytes; max {_MAX_BYTES})")

    is_pdf = data.startswith(_PDF_MAGIC) or (filename or "").lower().endswith(".pdf")
    text = _extract_pdf(data) if is_pdf else _decode_text(data)

    text = text.strip()
    if not text:
        # A PDF that parsed but yielded nothing is almost always a scan (image-only, no text layer).
        raise ResumeError(
            "no extractable text (a scanned/image PDF? upload a text PDF or paste text)"
            if is_pdf
            else "no extractable text"
        )
    return _within_char_cap(text)


def clean_resume_text(text: str) -> str:
    """Validate résumé text that arrived *as text* (the paste path), or raise `ResumeError`.

    The sibling of `extract_resume_text` for input needing no decoding. It shares that function's
    tail — strip, reject empty, enforce `_MAX_CHARS` — so the pasted path cannot drift from the
    uploaded one; everything downstream (`resume_version`, the D-085 identical-content no-op, the
    rolling reupload clock) keys on this returned text and is therefore unchanged by construction.

    There is no byte ceiling here: the caller already holds a decoded `str`, and the transport
    bounds the field long before `_MAX_CHARS` does (Starlette caps a non-file multipart part at
    1 MiB, above the ~800 KiB worst case of `_MAX_CHARS` UTF-8 characters).
    """
    cleaned = text.strip()
    if not cleaned:
        raise ResumeError("no résumé text")
    return _within_char_cap(cleaned)


def _within_char_cap(text: str) -> str:
    """The one length check, shared by both entry points; the boundary itself is accepted."""
    if len(text) > _MAX_CHARS:
        raise ResumeError(f"résumé too long ({len(text)} chars; max {_MAX_CHARS})")
    return text


def _extract_pdf(data: bytes) -> str:
    """Join the text layer of every page; raise `ResumeError` on an unreadable/encrypted PDF."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError, OSError) as exc:
        raise ResumeError(f"could not read PDF: {exc}") from exc


def _decode_text(data: bytes) -> str:
    """Decode an upload as UTF-8 text (markdown is text too); raise `ResumeError` if it isn't."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResumeError("file is not UTF-8 text (upload a .txt, .md, or text PDF)") from exc
