"""Truthfulness guard for AI-rewritten text.

An AI rewrite is accepted only if it introduces nothing that isn't supported by the source material:
  * no new numbers / percentages (invented metrics),
  * no new known skills/tools,
  * no new capitalised names (employers, universities, certifications) not present in the source.
Rejected rewrites fall back to the original text, and the reason is recorded.
"""
from __future__ import annotations

import re

from ..services.skills import find_skills

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z&.]+(?:\s+[A-Z][a-zA-Z&.]+)*\b")
# capitalised words that are fine at a sentence start etc.
_COMMON = {"I", "The", "A", "An", "And", "With", "For", "In", "On", "To", "Of", "At", "By", "As", "From", "Using",
           "Built", "Created", "Prepared", "Automated", "Developed", "Designed", "Managed", "Led", "Delivered",
           "Improved", "Reduced", "Increased", "Analysed", "Analyzed", "Maintained", "Tracked", "Validated",
           "Reconciled", "Streamlined", "Consolidated", "Produced", "Generated", "Presented", "Supported",
           "Coordinated", "Monitored", "Collaborated", "Performed", "Implemented", "Reviewed", "Ensured", "Hi",
           "Hello", "Dear", "Thanks", "Thank", "Regards", "Best", "Sincerely", "Subject", "Application", "Resume",
           "Summary", "Skills", "Experience", "Education", "Team", "Hiring", "Manager", "HR", "Monday", "Tuesday",
           "Wednesday", "Thursday", "Friday", "This", "My", "Would", "Looking", "Happy", "Please", "Could", "Also",
           "Currently", "Over", "Across", "Worked", "Handled", "Wrote", "Cleaned", "Merged", "Forecast", "Excel",
           "Data", "Reports", "Report", "Dashboard", "Dashboards", "Daily", "Weekly", "Monthly", "Key", "Strong"}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUM_RE.findall(text or "")}


def _propers(text: str) -> set[str]:
    out = set()
    for m in _PROPER_RE.findall(text or ""):
        for w in m.split():
            if w not in _COMMON and len(w) > 1:
                out.add(w.lower().strip("."))
    return out


def check(original_source: str, rewritten: str, allowed_extra: str = "") -> tuple[bool, str]:
    """Return (ok, reason). `original_source` = everything the text may draw on (resume + profile + JD facts)."""
    source = f"{original_source}\n{allowed_extra}"
    new_nums = _numbers(rewritten) - _numbers(source)
    if new_nums:
        return False, f"introduced numbers not in your resume: {', '.join(sorted(new_nums))}"
    new_skills = find_skills(rewritten) - find_skills(source)
    if new_skills:
        return False, f"introduced skills not in your resume: {', '.join(sorted(new_skills))}"
    new_names = _propers(rewritten) - _propers(source) - {w.lower() for w in _COMMON}
    source_lower = source.lower()
    new_names = {n for n in new_names if n not in source_lower}
    if new_names:
        return False, f"introduced names not in your resume: {', '.join(sorted(new_names))}"
    return True, ""


SYSTEM_PROMPT = (
    "You are a careful resume and job-application writing assistant for an Indian job seeker. "
    "Rewrite only what you are given. Never add skills, tools, employers, job titles, degrees, certifications, "
    "numbers, percentages or achievements that are not explicitly in the source text. If the source has no metric, "
    "do not invent one. Write in plain, natural, professional English. Avoid cliches like 'I hope this email finds "
    "you well', 'passionate', 'synergy', 'leverage', 'dynamic'. Return only the requested text, no commentary."
)
