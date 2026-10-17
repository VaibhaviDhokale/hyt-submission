"""Structured outputs the LLM must return. Validated with pydantic; anything else is rejected and retried."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

EduLevel = Literal["none", "high_school", "associate", "bachelor", "master", "doctorate"]


# ---------------------------------------------------------------- job description -> checklist
class Requirement(BaseModel):
    text: str = Field(description="the requirement in a few words, e.g. 'CPA license' or 'month-end close'")
    kind: Literal["must", "nice"] = Field(description="must = stated as required; nice = preferred/plus/bonus")
    category: Literal["credential", "software", "skill", "domain", "experience", "education"]
    min_years: Optional[float] = Field(None, description="only for category=experience: years asked for")
    min_education: Optional[EduLevel] = Field(None, description="only for category=education")
    jd_quote: str = Field(description="verbatim phrase from the posting this requirement comes from")


class JobChecklist(BaseModel):
    seniority: Literal["entry", "associate", "senior", "manager", "director"]
    location: Optional[str] = None
    remote: Optional[bool] = None
    requirements: list[Requirement] = Field(description="4 to 10 distinct, checkable requirements")


# ---------------------------------------------------------------- resume -> profile
class Role(BaseModel):
    title: str
    start: Optional[str] = Field(None, description="YYYY-MM or YYYY as written; null if absent")
    end: Optional[str] = Field(None, description="YYYY-MM, YYYY, or 'present'; null if absent")
    finance_relevant: bool = Field(description="accounting, finance, audit, tax, payroll, AP/AR, banking ops roles")
    internship: bool = False


class Education(BaseModel):
    level: EduLevel
    field: Optional[str] = None
    year: Optional[str] = None


class Profile(BaseModel):
    headline: str = Field(description="the resume's own title/headline")
    skills: list[str] = Field(description="skills as written, max 30")
    software: list[str] = Field(description="named tools/systems: Excel, QuickBooks, SAP, Oracle, ADP, ...")
    certifications: list[str] = Field(description="CPA, CMA, CIA, EA, ... only if held or explicitly in progress")
    education: list[Education]
    roles: list[Role]
    location: Optional[str] = Field(None, description="city/state as written; null if masked or absent")


# ---------------------------------------------------------------- (requirement, passages) -> verdicts
class Verdict(BaseModel):
    req: str = Field(description="requirement id, e.g. R3")
    verdict: Literal["met", "partial", "not_met"]
    quote: str = Field(description="exact words copied from ONE passage that support the verdict; '' if not_met")
    note: str = Field(description="max 15 words: why")


class Grading(BaseModel):
    verdicts: list[Verdict]


# ---------------------------------------------------------------- LLM-as-judge for explanations
class JudgeScore(BaseModel):
    grounded: int = Field(ge=1, le=5, description="every claim supported by the resume evidence shown")
    gaps_correct: int = Field(ge=1, le=5, description="the gaps named are real and complete")
    actionable: int = Field(ge=1, le=5, description="a recruiter can act on it without opening the resume")
    rationale: str = Field(description="max 30 words")


SCHEMAS = {"checklist": JobChecklist, "profile": Profile, "grade": Grading, "judge": JudgeScore}
