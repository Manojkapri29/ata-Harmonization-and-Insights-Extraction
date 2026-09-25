"""Outreach drafts: HR email, WhatsApp, LinkedIn connection note (<=300 chars), LinkedIn DM, cover letter,
and follow-ups. Drafts only - nothing is ever sent without the user explicitly confirming.

Messages are built from real facts (profile + resume + the job). Wording is varied per job so a batch of
messages doesn't read like a template, and common AI-sounding phrases are avoided.
"""
from __future__ import annotations

import hashlib
import re

from ..ai.guard import SYSTEM_PROMPT, check
from ..ai.providers import AIError, AIProvider
from .matching import Candidate
from .normalize import NCR, cities_in
from .skills import AREA_SKILLS, find_skills
from .tailor import strengthen_bullet

LINKEDIN_NOTE_LIMIT = 300
CHANNELS = ["email", "whatsapp", "linkedin_note", "linkedin_dm", "cover_letter"]
BANNED = ["i hope this email finds you well", "i am writing to express", "passionate", "synergy", "leverage",
          "dynamic environment", "esteemed organization", "kindly revert", "please find attached herewith"]


def _a(word: str) -> str:
    """'a'/'an' for a job title: an MIS Executive, an Analyst, a Data Analyst."""
    w = word.strip()
    first = w.split(" ")[0] if w else ""
    vowel_sound = (first[:1].lower() in "aeio" or (first.isupper() and len(first) > 1 and first[0] in "AEFHILMNORSX"))
    return f"{'an' if vowel_sound else 'a'} {w}"


def _tidy(text: str) -> str:
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)       # "Co.." -> "Co."
    return re.sub(r"[ \t]+\n", "\n", text)


def _pick(options: list[str], seed: str) -> str:
    return options[int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(options)]


def _first_name(full: str) -> str:
    return (full or "").strip().split(" ")[0] if full and full.strip() else ""


def _years(c: Candidate) -> str:
    if c.years is None:
        return ""
    return f"{int(c.years)}+ years" if c.years >= 1 else "hands-on experience"


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def _top_skills(c: Candidate, job, match: dict | None, n: int = 3) -> list[str]:
    """Tools the candidate has that this job asks for, most specific first (e.g. Power BI over Excel)."""
    text = f"{job.title}\n{job.description}".lower()
    job_sk = find_skills(text)
    have = [s for s in job_sk if s in c.skills and s not in AREA_SKILLS]
    # order by first mention in the JD, then drop generic ones implied by a specific one
    have.sort(key=lambda s: min((text.find(a) for a in [s.lower(), s.split("/")[0].lower()] if text.find(a) >= 0),
                                default=10**6))
    if "Advanced Excel" in have and "Excel" in have:
        have.remove("Excel")
    have = [s for s in have if s not in ("MS Office",)]
    if len(have) < n:
        have += [s for s in sorted(c.skills) if s not in AREA_SKILLS and s not in have and s not in ("Excel", "MS Office")]
    return have[:n]


def _evidence(resume_parsed: dict | None, job) -> str:
    """The resume bullet most relevant to this job (used verbatim, lightly adapted)."""
    if not resume_parsed:
        return ""
    job_sk = find_skills(f"{job.title}\n{job.description}")
    best, best_score = "", 0
    for e in resume_parsed.get("experience", []):
        for b in e.get("responsibilities", []):
            score = 3 * len(find_skills(b) & job_sk) + (2 if re.search(r"\d", b) else 0)
            if score > best_score:
                best, best_score = b, score
    return strengthen_bullet(best)[0] if best else ""


def _lower_first(s: str) -> str:
    return s[0].lower() + s[1:] if s and len(s) > 1 and s[1].islower() else s


def _location_line(c: Candidate, job) -> str:
    job_cities = cities_in(job.location or "")
    if job.remote or not job_cities:
        return ""
    home = cities_in(c.location)
    for p in c.preferred_locations:
        home |= cities_in(p)
    wants_ncr = "Delhi NCR" in home or bool(home & NCR)
    city = sorted(job_cities - {"Delhi NCR"} or job_cities)[0]
    if job_cities & home or (wants_ncr and job_cities & (NCR | {"Delhi NCR"})):
        if c.location:
            return f"I'm based in {c.location}, so {city} works well for me." if city not in c.location else ""
        return f"{city} is one of my preferred locations."
    return f"I'm open to relocating to {city} for this role."


def _focus(c: Candidate) -> str:
    """What the candidate does, from their own skills (e.g. 'MIS reporting and data analysis')."""
    areas = [label for skill, label in (("MIS Reporting", "MIS reporting"), ("Data Analysis", "data analysis"),
                                        ("Business Analysis", "business analysis"),
                                        ("Dashboard Development", "dashboard development"),
                                        ("Management Reporting", "management reporting")) if skill in c.skills]
    return _join(areas[:2]) or (c.headline.split("|")[0].strip().lower() if c.headline else "")


def _notice(c: Candidate) -> str:
    n = (c.notice_period or "").lower()
    if "immediate" in n:
        return "I can join immediately."
    return f"My notice period is {c.notice_period}." if c.notice_period else ""


def _signature(c: Candidate) -> str:
    return "\n".join(x for x in [c.name, " | ".join(x for x in (c.phone, c.email) if x), c.linkedin] if x)


# ---------------------------------------------------------------- generators

def email(c: Candidate, job, match: dict | None, resume_parsed: dict | None, contact=None) -> dict:
    seed = f"{job.id}-email"
    hi = f"Hi {_first_name(contact.name)}," if contact is not None and contact.name else "Hello Hiring Team,"
    skills = _top_skills(c, job, match)
    yrs = _years(c)
    opener = _pick([
        f"I came across the {job.title} opening at {job.company} and wanted to reach out directly.",
        f"I'm applying for the {job.title} role at {job.company} and wanted to introduce myself.",
        f"I saw that {job.company} is hiring {_a(job.title)}, and it lines up closely with the work I do.",
    ], seed)
    exp_line = (f"I have {yrs} of experience in {_focus(c)}, working day to day with {_join(skills)}."
                if yrs else f"I work day to day with {_join(skills)}.")
    ev = _evidence(resume_parsed, job)
    ev_line = f"Most recently, I {_lower_first(ev)}." if ev else ""
    close = _pick(["Would you be open to a short call this week?", "I'd be glad to talk whenever it suits you.",
                   "Happy to share more details or take a quick call."], seed)
    body = "\n\n".join(x for x in [
        hi, opener, " ".join(x for x in [exp_line, ev_line] if x),
        " ".join(x for x in [_location_line(c, job), _notice(c)] if x),
        f"My resume, tailored to this role, is attached. {close}", f"Thanks,\n{_signature(c)}"] if x)
    return {"channel": "email", "subject": f"Application for {job.title} – {c.name}", "body": body}


def whatsapp(c: Candidate, job, match: dict | None, resume_parsed: dict | None, contact=None) -> dict:
    name = _first_name(contact.name) if contact is not None and contact.name else ""
    skills = _top_skills(c, job, match)
    yrs = _years(c)
    parts = [f"Hi {name}," if name else "Hello,",
             f"I'm {c.name}. I've applied for the {job.title} role at {job.company}."]
    parts.append(f"I have {yrs} in {_focus(c)} ({', '.join(skills)})." if yrs
                 else f"I work with {', '.join(skills)}.")
    if _notice(c):
        parts.append(_notice(c))
    parts.append(_pick(["Could I share my resume here?", "May I send you my resume?",
                        "Would it be okay to share my resume with you?"], f"{job.id}-wa"))
    parts.append("Thank you!")
    return {"channel": "whatsapp", "subject": "", "body": " ".join(parts)}


def linkedin_note(c: Candidate, job, match: dict | None, resume_parsed: dict | None, contact=None) -> dict:
    name = _first_name(contact.name) if contact is not None and contact.name else ""
    skills = _top_skills(c, job, match, 3)
    yrs = _years(c)
    candidates = [
        f"Hi {name or 'there'}, I applied for the {job.title} role at {job.company}. I have {yrs} in {_focus(c)} "
        f"with {_join(skills)}. Would be glad to connect.",
        f"Hi {name or 'there'}, I applied for the {job.title} role at {job.company}. I work with {_join(skills[:2])} "
        f"and would be glad to connect.",
        f"Hi {name or 'there'}, I applied for the {job.title} role at {job.company} and would be glad to connect.",
    ]
    if not yrs:
        candidates = candidates[1:]
    body = next((t for t in candidates if len(t) <= LINKEDIN_NOTE_LIMIT), candidates[-1][:LINKEDIN_NOTE_LIMIT])
    return {"channel": "linkedin_note", "subject": "", "body": body}


def linkedin_dm(c: Candidate, job, match: dict | None, resume_parsed: dict | None, contact=None) -> dict:
    name = _first_name(contact.name) if contact is not None and contact.name else ""
    skills = _top_skills(c, job, match)
    yrs = _years(c)
    ev = _evidence(resume_parsed, job)
    lines = [f"Hi {name}," if name else "Hi,",
             f"Thanks for connecting. I've applied for the {job.title} position at {job.company}"
             + (" and wanted to share a bit of context." if ev or yrs else ".")]
    if yrs:
        lines.append(f"Over the past {yrs} I've worked on {_focus(c)}, mainly with {_join(skills)}.")
    if ev:
        lines.append(f"For example, I {_lower_first(ev)}.")
    tail = " ".join(x for x in [_notice(c), "If it helps, I can send my resume here as well."] if x)
    lines.append(tail)
    lines.append(f"Thanks,\n{c.name}")
    return {"channel": "linkedin_dm", "subject": "", "body": "\n\n".join(lines)}


def cover_letter(c: Candidate, job, match: dict | None, resume_parsed: dict | None, contact=None) -> dict:
    hi = f"Dear {contact.name}," if contact is not None and contact.name else "Dear Hiring Manager,"
    skills = _top_skills(c, job, match, 4)
    yrs = _years(c)
    ev = _evidence(resume_parsed, job)
    p1 = (f"I'd like to apply for the {job.title} role at {job.company}. " +
          (f"I have {yrs} of experience in {_focus(c)}, and the role's focus on "
           f"{_join(skills[:2])} matches the work I do every day." if yrs else
           f"The role's focus on {_join(skills[:2])} matches the work I do."))
    p2 = " ".join(x for x in [
        f"In my current work I {_lower_first(ev)}." if ev else "",
        f"I'm comfortable with {_join(skills)}, and I care about getting numbers right before they reach a decision-maker."
        if skills else ""] if x)
    edu = f"I also hold an {c.education[0]}." if c.education and c.education[0].lower().startswith(("mba", "m")) else \
        (f"I hold a {c.education[0]}." if c.education else "")
    p3 = " ".join(x for x in [edu, _location_line(c, job), _notice(c)] if x)
    p4 = f"Thank you for considering my application. I'd welcome the chance to discuss how I can help {job.company}."
    body = "\n\n".join(x for x in [hi, p1, p2, p3, p4, f"Sincerely,\n{c.name}"] if x)
    return {"channel": "cover_letter", "subject": f"Cover letter – {job.title} – {c.name}", "body": body}


def followup(c: Candidate, job, day: int, channel: str, contact=None) -> dict:
    name = _first_name(contact.name) if contact is not None and contact.name else ""
    hi = f"Hi {name}," if name else "Hello,"
    if day <= 3:
        body = (f"{hi} I applied for the {job.title} role at {job.company} a few days ago and wanted to check if my "
                f"profile is being considered. Happy to share anything else you need. Thank you! - {c.name}")
        return {"channel": "followup_message", "subject": "", "body": body}
    if day <= 7:
        body = (f"{hi}\n\nI'm following up on my application for the {job.title} position at {job.company}, sent last "
                f"week. I'm still very interested in the role and would be glad to discuss how my experience in "
                f"{_join(_top_skills(c, job, None, 2))} fits your needs.\n\n{_notice(c)}\n\nThanks,\n{_signature(c)}")
        return {"channel": "followup_email", "subject": f"Following up: {job.title} application – {c.name}",
                "body": re.sub(r"\n{3,}", "\n\n", body)}
    body = (f"{hi}\n\nI wanted to follow up one last time on my application for the {job.title} role at "
            f"{job.company}. If the position has been filled, no problem at all; I'd appreciate being considered for "
            f"similar roles in the future.\n\nThank you for your time,\n{_signature(c)}")
    return {"channel": "followup_email", "subject": f"{job.title} application – {c.name}", "body": body}


GENERATORS = {"email": email, "whatsapp": whatsapp, "linkedin_note": linkedin_note, "linkedin_dm": linkedin_dm,
              "cover_letter": cover_letter}


def generate(channel: str, c: Candidate, job, match: dict | None, resume_parsed: dict | None, contact=None,
             ai: AIProvider | None = None, source_text: str = "") -> dict:
    draft = GENERATORS[channel](c, job, match, resume_parsed, contact)
    draft["generated_by"] = "template"
    if ai is not None and ai.available:
        draft = _ai_polish(draft, c, job, ai, source_text)
    draft["body"] = _tidy(draft["body"])
    draft["warnings"] = [f"Contains '{b}'" for b in BANNED if b in draft["body"].lower()]
    if channel == "linkedin_note" and len(draft["body"]) > LINKEDIN_NOTE_LIMIT:
        draft["body"] = draft["body"][:LINKEDIN_NOTE_LIMIT - 1].rsplit(" ", 1)[0] + "."
    return draft


def _ai_polish(draft: dict, c: Candidate, job, ai: AIProvider, source_text: str) -> dict:
    limit = " Keep it under 300 characters." if draft["channel"] == "linkedin_note" else ""
    try:
        text = ai.generate(SYSTEM_PROMPT, (
            f"Make this {draft['channel'].replace('_', ' ')} sound natural and personal, like a real person wrote it. "
            f"Keep every fact exactly; do not add any new facts, numbers or skills.{limit}\n\nDRAFT:\n{draft['body']}"),
            max_tokens=900).strip()
    except AIError as e:
        draft["ai_note"] = str(e)
        return draft
    facts = "\n".join([source_text, draft["body"], job.title, job.company, job.description or ""])
    ok, why = check(facts, text)
    if ok and text:
        return {**draft, "body": text, "generated_by": f"ai:{ai.name}"}
    draft["ai_note"] = f"AI version rejected ({why}); showing template version."
    return draft
