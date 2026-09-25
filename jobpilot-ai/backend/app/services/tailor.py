"""Resume optimisation.

Two outputs from the same truthful source (parsed master resume + your profile):
  * ATS-optimised resume   - clean structure, stronger verbs, organised skills. No job needed.
  * Job-specific resume    - the above, plus JD-relevant skills/bullets/projects first.

Rules: we reorder, select, fix weak phrasing and surface skills you already listed. We never add a skill,
number, employer, title, degree or achievement that is not in your resume or profile. Optional AI rewriting
goes through ai.guard.check and falls back to the original on any violation.
"""
from __future__ import annotations

import re

from ..ai.guard import SYSTEM_PROMPT, check
from ..ai.providers import AIError, AIProvider
from .skills import canonical_skill, expand_implied, find_skills, jd_keywords, role_category

IRREGULAR = {"making": "made", "building": "built", "running": "ran", "writing": "wrote", "leading": "led",
             "doing": "did", "taking": "took", "sending": "sent", "getting": "got", "keeping": "kept",
             "bringing": "brought", "giving": "gave", "setting": "set", "putting": "put", "meeting": "met",
             "using": "used", "sharing": "shared", "preparing": "prepared", "ensuring": "ensured",
             "handling": "handled", "managing": "managed", "creating": "created", "updating": "updated",
             "validating": "validated", "coordinating": "coordinated", "automating": "automated",
             "generating": "generated", "compiling": "compiled", "analysing": "analysed", "analyzing": "analyzed",
             "reconciling": "reconciled", "consolidating": "consolidated", "producing": "produced",
             "monitoring": "monitored", "tracking": "tracked", "maintaining": "maintained", "planning": "planned"}


def _past(gerund: str) -> str:
    g = gerund.lower()
    if g in IRREGULAR:
        return IRREGULAR[g]
    stem = g[:-3]
    if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiouls":
        stem = stem[:-1]           # planning -> plan
        return stem + stem[-1] + "ed"
    return stem + ("ed" if not stem.endswith("e") else "d")


def strengthen_bullet(text: str) -> tuple[str, bool]:
    """Deterministic, meaning-preserving fixes. Returns (new_text, changed)."""
    original = text.strip()
    t = original.rstrip(".").strip()
    m = re.match(r"^(?:was\s+)?(?:responsible for|in charge of|tasked with|involved in|duties included)\s+(?:the\s+)?(\w+ing)\b\s*(.*)$",
                 t, re.I)
    if m:
        t = f"{_past(m.group(1)).capitalize()} {m.group(2)}".strip()
    else:
        m = re.match(r"^(?:responsible for|in charge of)\s+(.*)$", t, re.I)
        if m:
            t = f"Owned {m.group(1)}"
        else:
            m = re.match(r"^worked on\s+(\w+ing)\b\s*(.*)$", t, re.I)
            if m:
                t = f"{_past(m.group(1)).capitalize()} {m.group(2)}".strip()
    t = re.sub(r"\s{2,}", " ", t)
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t, t != original.rstrip(".").strip()


# ---------------------------------------------------------------- helpers

def _relevance(text: str, jd_skills: set[str], jd_kws: list[str]) -> int:
    lower = text.lower()
    return 3 * len(find_skills(text) & jd_skills) + sum(1 for k in jd_kws if " " in k and k in lower)


def truthful_skills(parsed: dict, profile) -> list[str]:
    ordered: list[str] = []
    for s in list(parsed.get("skills", [])) + list(getattr(profile, "skills", None) or []):
        c = canonical_skill(s)
        if c and c not in ordered:
            ordered.append(c)
    return ordered


def _years(parsed: dict, profile) -> float | None:
    y = getattr(profile, "total_experience_years", None)
    return y if y is not None else parsed.get("total_experience_years")


def build_summary(parsed: dict, profile, skills_first: list[str], job_title: str = "") -> str:
    years = _years(parsed, profile)
    exp = parsed.get("experience", [])
    recent = exp[0].get("designation", "") if exp else ""
    areas = [s for s in skills_first if s in ("MIS Reporting", "Management Reporting", "Data Analysis",
                                                 "Dashboard Development", "Reporting Automation", "Data Validation",
                                                 "Business Analysis", "Data Visualization", "KPI Tracking")][:3]
    tools = [s for s in skills_first if s not in areas][:5]
    who = recent or (getattr(profile, "headline", "") or "Professional")
    parts = []
    lead = f"{who} with {years:g}+ years of experience" if years else f"{who} with hands-on experience"
    parts.append(f"{lead} in {_join([a.lower() if a not in ('MIS Reporting',) else 'MIS reporting' for a in areas])}."
                 if areas else f"{lead}.")
    if tools:
        parts.append(f"Hands-on with {_join(tools)}.")
    edu = getattr(profile, "education", None) or [e.get("degree", "") for e in parsed.get("education", [])[:1]]
    if edu and edu[0]:
        parts.append(f"{edu[0]}.")
    notice = getattr(profile, "notice_period", "")
    if notice and "immediate" in notice.lower():
        parts.append("Available to join immediately.")
    return " ".join(parts)


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# ---------------------------------------------------------------- main

def optimize(parsed: dict, profile, job=None, ai: AIProvider | None = None, max_bullets: int = 5,
             max_projects: int = 3, source_text: str = "") -> dict:
    """Return {"resume": {...}, "changes": [...], "keywords_added": [...], "ai_used": bool}."""
    jd_text = f"{job.title}\n{job.description}" if job is not None else ""
    jd_sk = expand_implied(find_skills(jd_text)) if jd_text else set()
    jd_kws = jd_keywords(jd_text) if jd_text else []
    changes: list[str] = []

    # skills: truthful pool, JD-relevant first
    pool = truthful_skills(parsed, profile)
    original_skill_text = " ".join(parsed.get("skills", []))
    if jd_sk:
        core = [s for s in pool if s in jd_sk]
        other = [s for s in pool if s not in jd_sk]
        skills = core + other
        keywords_added = [s for s in core if s not in find_skills(source_text or original_skill_text)
                          and s not in parsed.get("skills", [])]
        if core:
            changes.append(f"Moved {len(core)} JD-relevant skills to the front: {', '.join(core[:8])}.")
        if keywords_added:
            changes.append(f"Surfaced skills from your profile that the resume didn't list: {', '.join(keywords_added)}.")
        missing = sorted(s for s in find_skills(jd_text) - expand_implied(set(pool)))
        if missing:
            changes.append(f"NOT added (not in your resume/profile): {', '.join(missing)}. Add only if true.")
    else:
        skills, core, keywords_added = pool, [], []

    # experience: strengthen verbs, rank bullets by JD relevance
    experience = []
    for e in parsed.get("experience", []):
        bullets = []
        for b in e.get("responsibilities", []):
            nb, changed = strengthen_bullet(b)
            if changed:
                changes.append(f"Rephrased: \"{b[:70]}\" -> \"{nb[:70]}\"")
            bullets.append(nb)
        if jd_sk:
            bullets = sorted(bullets, key=lambda x: -_relevance(x, jd_sk, jd_kws))
        if len(bullets) > max_bullets:
            changes.append(f"Kept the {max_bullets} most relevant bullets for {e.get('designation') or e.get('company')}.")
            bullets = bullets[:max_bullets]
        experience.append({"designation": e.get("designation", ""), "company": e.get("company", ""),
                           "location": e.get("location", ""), "duration": e.get("duration", ""), "bullets": bullets})

    projects = [{"name": p.get("name", ""), "tech": p.get("tech", []),
                 "bullets": [strengthen_bullet(b)[0] for b in p.get("bullets", [])]} for p in parsed.get("projects", [])]
    if jd_sk and projects:
        projects.sort(key=lambda p: -_relevance(" ".join([p["name"], *p["tech"], *p["bullets"]]), jd_sk, jd_kws))
    if len(projects) > max_projects:
        changes.append(f"Kept the {max_projects} most relevant projects.")
        projects = projects[:max_projects]

    summary = build_summary(parsed, profile, core or skills, job.title if job is not None else "")
    changes.append("Rewrote the summary from facts in your resume/profile.")

    top = (core or skills)[:3]
    recent = experience[0]["designation"] if experience else ""
    headline = " | ".join([x for x in [recent or getattr(profile, "headline", ""), *top] if x])

    contact = dict(parsed.get("contact", {}))
    for key, attr in (("email", "email"), ("phone", "phone"), ("linkedin", "linkedin_url"), ("location", "location")):
        if getattr(profile, attr, "") and not contact.get(key):
            contact[key] = getattr(profile, attr)

    resume = {
        "name": getattr(profile, "full_name", "") or parsed.get("name", ""), "headline": headline, "contact": contact,
        "summary": summary, "skills_core": core, "skills": [s for s in skills if s not in core] if core else skills,
        "experience": experience, "projects": projects,
        "education": [{k: e.get(k, "") for k in ("degree", "institution", "year", "score")} for e in parsed.get("education", [])],
        "certifications": list(parsed.get("certifications", [])),
    }
    if not resume["education"] and getattr(profile, "education", None):
        resume["education"] = [{"degree": d, "institution": "", "year": "", "score": ""} for d in profile.education]

    ai_used = False
    if ai is not None and ai.available:
        ai_used = _ai_polish(resume, source_text, jd_text, ai, changes)
    return {"resume": resume, "changes": changes, "keywords_added": keywords_added, "ai_used": ai_used,
            "role_category": role_category(job.title) if job is not None else ""}


def _ai_polish(resume: dict, source_text: str, jd_text: str, ai: AIProvider, changes: list[str]) -> bool:
    """Ask the AI to rephrase summary + bullets; accept each piece only if the guard passes."""
    used = False
    facts = source_text + "\n" + resume["summary"]
    try:
        new_summary = ai.generate(SYSTEM_PROMPT, (
            "Rewrite this resume summary in 2-3 sentences, natural and specific, aligned to the job below. "
            "Use ONLY facts from the source.\n\nSOURCE RESUME:\n" + source_text[:6000] +
            "\n\nCURRENT SUMMARY:\n" + resume["summary"] + "\n\nJOB:\n" + jd_text[:3000]), max_tokens=600).strip()
        ok, why = check(facts, new_summary)
        if ok and new_summary:
            resume["summary"] = new_summary
            used = True
            changes.append("AI polished the summary (verified: no new facts).")
        elif new_summary:
            changes.append(f"AI summary rejected ({why}); kept rule-based summary.")
    except AIError as e:
        changes.append(f"AI unavailable ({e}); used rule-based text.")
        return False
    for role in resume["experience"]:
        for i, b in enumerate(role["bullets"]):
            try:
                nb = ai.generate(SYSTEM_PROMPT, (
                    "Rewrite this resume bullet: start with a strong past-tense verb, keep it under 25 words, "
                    "use the job's wording only where it means the same thing. Do not add numbers or tools.\n\n"
                    f"BULLET: {b}\n\nJOB KEYWORDS: {', '.join(jd_keywords(jd_text, 15))}"), max_tokens=200).strip().strip("-• ")
            except AIError:
                return used
            ok, why = check(source_text + "\n" + b, nb)
            if ok and nb and nb != b:
                role["bullets"][i] = nb
                used = True
            elif nb and not ok:
                changes.append(f"AI rewrite rejected for \"{b[:50]}...\" ({why}).")
    return used
