"""Explainable job <-> candidate matching.

Weights (from the product spec):
    role 25, skills 25, experience 15, location 10, salary 10, education 5, JD keywords 10

Each component is scored 0-100 with a plain-English reason. Unknown information (e.g. no salary in the
posting) gets a neutral score and is listed under "unclear" instead of being guessed.
The result is a ranking aid, not a prediction of interview selection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import NCR, REMOTE_RE, cities_in, is_india
from .skills import (canonical_skill, contains_keyword, expand_implied, find_skills, jd_keywords, role_category,
                     title_tokens)

WEIGHTS = {"role": 25, "skills": 25, "experience": 15, "location": 10, "salary": 10, "education": 5, "keywords": 10}
DISCLAIMER = "Match score is an estimate to help you prioritise. It does not predict interview selection."


@dataclass
class Candidate:
    name: str
    years: float | None
    skills: set[str]
    target_roles: list[str]
    preferred_locations: list[str]
    open_to_remote: bool = True
    open_to_relocation: bool = True
    current_salary_monthly: int | None = None
    expected_salary_monthly: int | None = None
    education: list[str] = field(default_factory=list)
    designations: list[str] = field(default_factory=list)
    text: str = ""
    notice_period: str = ""
    location: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    headline: str = ""


def build_candidate(profile, resume_parsed: dict | None = None, resume_text: str = "") -> Candidate:
    rp = resume_parsed or {}
    skills = {canonical_skill(s) for s in (profile.skills or [])}
    skills |= {canonical_skill(s) for s in rp.get("skills", [])}
    text = "\n".join([profile.summary or "", " ".join(profile.skills or []), resume_text or ""])
    skills |= find_skills(text)
    years = profile.total_experience_years if profile.total_experience_years is not None else rp.get("total_experience_years")
    return Candidate(
        name=profile.full_name, years=years, skills=expand_implied(skills), target_roles=list(profile.target_roles or []),
        preferred_locations=list(profile.preferred_locations or []), open_to_remote=profile.open_to_remote,
        open_to_relocation=profile.open_to_relocation_if_relevant,
        current_salary_monthly=profile.current_salary_monthly, expected_salary_monthly=profile.expected_salary_monthly,
        education=list(profile.education or []) + [e.get("degree", "") for e in rp.get("education", []) if e.get("degree")],
        designations=[e.get("designation", "") for e in rp.get("experience", []) if e.get("designation")],
        text=text, notice_period=profile.notice_period or "", location=profile.location or "",
        email=profile.email or rp.get("contact", {}).get("email", ""), phone=profile.phone or rp.get("contact", {}).get("phone", ""),
        linkedin=profile.linkedin_url or rp.get("contact", {}).get("linkedin", ""), headline=profile.headline or "",
    )


# ---------------------------------------------------------------- components

def score_role(title: str, targets: list[str], designations: list[str]) -> tuple[int, str]:
    cat = role_category(title)
    target_cats = {role_category(t) for t in targets}
    if cat != "Other" and cat in target_cats:
        return 100, f"'{title}' is a {cat} role, one of your target roles."
    tt = title_tokens(title)
    best, best_role = 0.0, ""
    for role in targets + designations:
        rt = title_tokens(role)
        if tt and rt:
            overlap = len(tt & rt) / len(rt)
            if overlap > best:
                best, best_role = overlap, role
    if best >= 0.5:
        return int(60 + 40 * best), f"Title overlaps with '{best_role}'."
    if cat in ("Operations Analyst", "Financial Analyst", "Data Scientist"):
        return 45, f"'{title}' is an adjacent analytics role ({cat})."
    if best > 0:
        return 30, f"Title only partly related to your targets (closest: '{best_role}')."
    return 5, f"'{title}' does not look like any of your target roles."


def score_skills(job_skills: set[str], cand: set[str]) -> tuple[int, list[str], list[str], str]:
    if not job_skills:
        return 50, [], [], "The posting lists no recognisable skills."
    have = sorted(s for s in job_skills if s in cand)
    missing = sorted(s for s in job_skills if s not in cand)
    score = round(100 * len(have) / len(job_skills))
    return score, have, missing, f"You have {len(have)} of {len(job_skills)} skills the job mentions."


def score_experience(years: float | None, lo: float | None, hi: float | None) -> tuple[int, str, str | None]:
    if lo is None and hi is None:
        return 60, "The posting does not state required experience.", None
    if years is None:
        return 50, "Your total experience is not set in your profile.", "Set total experience in Settings > Profile."
    lo = lo or 0
    rng = f"{lo:g}-{hi:g}" if hi is not None else f"{lo:g}+"
    if years < lo:
        gap = lo - years
        concern = f"Asks for {rng} years; you have {years:g}."
        return max(0, round(100 - 35 * gap)), f"Slightly below the {rng} years asked." if gap <= 1 else concern, concern
    if hi is not None and years > hi:
        over = years - hi
        concern = f"Role targets {rng} years; you may be seen as over-qualified." if over > 2 else None
        return max(40, round(100 - 12 * over)), f"Above the {rng} year range.", concern
    return 100, f"Your {years:g} years fit the {rng} year requirement.", None


def score_location(job_loc: str, remote: bool | None, prefs: list[str], open_remote: bool,
                   relocate: bool) -> tuple[int, str]:
    loc_remote = bool(remote) or bool(REMOTE_RE.search(job_loc or ""))
    if loc_remote:
        return (100, "Remote role.") if open_remote else (40, "Remote role, but you did not select remote.")
    if not job_loc:
        return 50, "Location not stated."
    job_cities = cities_in(job_loc)
    pref_cities = set().union(*(cities_in(p) for p in prefs)) if prefs else set()
    wants_ncr = "Delhi NCR" in pref_cities
    if job_cities & pref_cities or (wants_ncr and job_cities & (NCR | {"Delhi NCR"})):
        return 100, f"{job_loc} is in your preferred locations."
    if is_india(job_loc):
        return (45, f"{job_loc} is outside your preferred cities (you are open to relocating for relevant roles).") \
            if relocate else (15, f"{job_loc} is outside your preferred cities.")
    return 10, f"{job_loc} is outside India and not remote."


def score_salary(job_min: float | None, job_max: float | None, currency: str, cur_monthly: int | None,
                 exp_monthly: int | None) -> tuple[int, str, str | None]:
    if job_min is None and job_max is None:
        return 50, "Salary not disclosed.", None
    if not (cur_monthly or exp_monthly):
        return 50, "Set your current/expected salary to compare.", None
    if currency and currency != "INR":
        return 60, f"Salary is in {currency}; not compared with your INR salary.", None
    top = job_max or job_min
    current_annual = (cur_monthly or 0) * 12
    target_annual = (exp_monthly or 0) * 12 or current_annual * 1.15
    if top >= target_annual:
        return 100, f"Pays up to ₹{top / 100000:.1f} L/yr, at or above your target.", None
    if top >= current_annual * 1.05:
        return 75, f"Pays up to ₹{top / 100000:.1f} L/yr, a modest raise over your current salary.", None
    if top >= current_annual * 0.95:
        return 45, "Pay is about the same as your current salary.", "Salary may not be an improvement."
    return 10, f"Pays up to ₹{top / 100000:.1f} L/yr, below your current ₹{current_annual / 100000:.1f} L/yr.", \
        "Salary is below your current pay."


def score_education(job_edu: str, cand_edu: list[str]) -> tuple[int, str, str | None]:
    if not job_edu:
        return 80, "No specific education requirement found.", None
    ce = " ".join(cand_edu).lower()
    has_pg = bool(re.search(r"\bmba\b|pgdm|master|post[- ]?grad|m\.?\s?tech|mca", ce))
    has_grad = has_pg or bool(re.search(r"bachelor|b\.?\s?com|bba|b\.?\s?tech|b\.?\s?sc|b\.?a\b|graduat", ce))
    needs = job_edu
    if "B.Tech" in needs and not re.search(r"b\.?\s?tech|b\.?e\b|engineer", ce) and "Any Graduate" not in needs \
            and "MBA" not in needs:
        return 30, f"Asks for {needs}.", f"Posting asks for {needs}."
    if "MBA" in needs and has_pg:
        return 100, "Your MBA matches the requirement.", None
    if has_grad:
        return 90, f"You meet the '{needs}' requirement.", None
    return 50, f"Check the education requirement ({needs}).", None


def score_keywords(description: str, cand_text: str, cand_skills: set[str]) -> tuple[int, list[str], list[str]]:
    kws = jd_keywords(description, limit=25)
    if not kws:
        return 50, [], []
    found, missing = [], []
    for k in kws:
        (found if (k in cand_skills or contains_keyword(cand_text, k)) else missing).append(k)
    return round(100 * len(found) / len(kws)), found, missing


# ---------------------------------------------------------------- overall

def match_job(job, cand: Candidate) -> dict:
    job_skills = set(job.skills or []) | find_skills(f"{job.title}\n{job.description}")
    job_skills = {canonical_skill(s) for s in job_skills}

    role, role_why = score_role(job.title, cand.target_roles, cand.designations)
    skills, have, missing, skills_why = score_skills(job_skills, cand.skills)
    exp, exp_why, exp_concern = score_experience(cand.years, job.experience_min, job.experience_max)
    loc, loc_why = score_location(job.location, job.remote, cand.preferred_locations, cand.open_to_remote,
                                  cand.open_to_relocation)
    sal, sal_why, sal_concern = score_salary(job.salary_min, job.salary_max, job.salary_currency,
                                             cand.current_salary_monthly, cand.expected_salary_monthly)
    edu, edu_why, edu_concern = score_education(job.education, cand.education)
    kw, kw_found, kw_missing = score_keywords(job.description, cand.text, cand.skills)

    parts = {"role": role, "skills": skills, "experience": exp, "location": loc, "salary": sal,
             "education": edu, "keywords": kw}
    overall = round(sum(parts[k] * w for k, w in WEIGHTS.items()) / sum(WEIGHTS.values()))

    concerns = [c for c in (exp_concern, sal_concern, edu_concern) if c]
    if loc < 40:
        concerns.append(loc_why)
    if missing:
        concerns.append(f"Not in your profile/resume: {', '.join(missing[:6])}.")
    if not job.description or len(job.description) < 300:
        concerns.append("Short job description - the score is less reliable.")
    unclear = [why for score, why in ((sal, sal_why), (exp, exp_why), (loc, loc_why)) if score in (50, 60)]

    reasons = [r for s, r in sorted([(role, role_why), (skills, skills_why), (exp, exp_why), (loc, loc_why),
                                     (sal, sal_why), (edu, edu_why)], key=lambda x: -x[0]) if s >= 70]

    if overall >= 80 and len(missing) <= 2:
        action = "Strong fit. Tailor your resume lightly and apply soon; reach out to HR."
    elif overall >= 65:
        action = "Good fit. Tailor your resume to the JD before applying."
    elif overall >= 50:
        action = "Partial fit. Apply only if the role interests you, and address the gaps honestly."
    else:
        action = "Low fit. Skip unless there's a specific reason to apply."

    return {
        "overall": overall,
        "components": {k: {"score": parts[k], "weight": w} for k, w in WEIGHTS.items()},
        "role_match": role, "skill_match": skills, "experience_match": exp, "location_match": loc,
        "salary_match": sal, "education_match": edu, "keyword_match": kw,
        "matching_skills": have, "missing_skills": missing,
        "matching_keywords": kw_found, "missing_keywords": kw_missing,
        "concerns": concerns, "unclear": unclear, "why": reasons,
        "explanations": {"role": role_why, "skills": skills_why, "experience": exp_why, "location": loc_why,
                         "salary": sal_why, "education": edu_why},
        "recommendation": action, "disclaimer": DISCLAIMER,
    }
