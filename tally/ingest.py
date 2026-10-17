"""Turn an uploaded file (PDF or text) into plain text, and a pasted posting into a job record."""
from __future__ import annotations

import io
import re

MAX_PDF_PAGES = 12
LEVELS = ("Internship", "Entry level", "Associate", "Mid-Senior level", "Director")


class IngestError(ValueError):
    pass


def file_text(name: str, data: bytes) -> str:
    """PDF -> text via pypdf (text layer only; scanned images are rejected, not OCR'd). Anything else is decoded as UTF-8."""
    if data[:5] == b"%PDF-" or name.lower().endswith(".pdf"):
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
        try:
            rd = PdfReader(io.BytesIO(data))
            if rd.is_encrypted:
                raise IngestError("This PDF is password-protected.")
            pages = [(p.extract_text() or "") for p in rd.pages[:MAX_PDF_PAGES]]
        except PyPdfError as e:
            raise IngestError(f"Could not read this PDF ({e.__class__.__name__}).") from e
        text = "\n".join(pages)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated at line ends
        if len(text.split()) < 20:
            raise IngestError("No text found in this PDF (a scan?). Paste the text instead.")
        return text
    return data.decode("utf-8", "replace")


def job_record(title: str, company: str, location: str, level: str, text: str, n: int) -> dict:
    title, text = title.strip(), text.strip()
    if not title:
        raise IngestError("Give the role a title.")
    if len(text.split()) < 40:
        raise IngestError("The job description is too short (need at least 40 words).")
    return {"id": f"N{n:02d}", "source_job_id": "", "title": title, "company": company.strip() or "Your company",
            "location": location.strip() or "Not stated", "level": level if level in LEVELS else "Not stated",
            "work_type": "Full-time", "text": text, "split": "new"}
