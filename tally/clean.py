"""Text hygiene: unicode cleanup, PII masking, prompt-injection flags. Pure functions, no I/O."""
from __future__ import annotations

import re
import unicodedata

INVISIBLE = re.compile(r"[​-‏ - ⁠-⁯﻿\U000e0000-\U000e007f]")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
STREET = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Drive|Dr|Lane|Ln)\b\.?")

# A first line that looks like a person's name ("Emily Walsh", "Mary J. Blige") is masked: names must never reach
# the LLM (fairness suite: under Gemini a name in the prompt flipped a decision). Title Case job titles are kept.
NAME_LINE = re.compile(r"^[A-Z][a-z'’-]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z'’-]+){1,2}$")
TITLE_WORDS = set("""accountant analyst manager specialist clerk controller auditor director assistant officer senior
staff bookkeeper consultant associate engineer administrator coordinator executive intern professional summary
history experience profile overview qualifications skills objective resume curriculum vitae payroll tax finance
financial accounting accounts receivable payable lead head chief vice president partner""".split())


def mask_name_header(text: str) -> tuple[str, int]:
    lines = text.split("\n", 1)
    first = lines[0].strip()
    if NAME_LINE.match(first) and not ({w.lower().strip(".") for w in first.split()} & TITLE_WORDS):
        return "[NAME]" + ("\n" + lines[1] if len(lines) > 1 else ""), 1
    return text, 0


# Instructions aimed at a model, not at a recruiter. Kept narrow: "ignore" alone is ordinary English.
INJECTION = re.compile(
    r"(ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts?)"
    r"|disregard (?:the|all|your) (?:instructions|rules|criteria)"
    r"|(?:you are|act as) (?:an? )?(?:ai\b|large language model|language model|screening (?:bot|system|model))"
    r"|(?:rate|score|rank|mark) (?:this|the|me|this candidate) (?:as )?(?:a |the )?(?:10|top|highest|perfect|met)"
    r"|system prompt|\bnew instructions\b)",
    re.I,
)


def normalize(text: str) -> tuple[str, int]:
    """NFKC, drop invisible characters, collapse runs of spaces. Returns (text, invisible_chars_removed)."""
    text = unicodedata.normalize("NFKC", text or "")
    removed = len(INVISIBLE.findall(text))
    text = INVISIBLE.sub("", text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip(), removed


def mask_pii(text: str) -> tuple[str, dict]:
    counts = {}
    for name, rx, token in [("email", EMAIL, "[EMAIL]"), ("url", URL, "[URL]"), ("ssn", SSN, "[ID]"),
                            ("phone", PHONE, "[PHONE]"), ("street", STREET, "[ADDRESS]")]:
        text, n = rx.subn(token, text)
        counts[name] = n
    return text, counts


def injection_hits(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in INJECTION.finditer(text)})


def resume_to_lines(raw: str) -> str:
    """Kaggle Resume_str is one long line with runs of spaces where line breaks were. Restore rough lines."""
    t = re.sub(r" {3,}", "\n", raw or "")
    return "\n".join(ln.strip() for ln in t.splitlines() if ln.strip())


def clean_resume(raw: str) -> dict:
    text, invisible = normalize(resume_to_lines(raw))
    text, pii = mask_pii(text)
    text, pii["name"] = mask_name_header(text)
    return {"text": text, "invisible_removed": invisible, "pii_masked": pii, "injection": injection_hits(text),
            "words": len(text.split())}
