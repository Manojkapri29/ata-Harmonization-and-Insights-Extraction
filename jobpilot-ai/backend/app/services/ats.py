"""ATS-style resume analysis. Produces an *ATS compatibility estimate*, never a guarantee.

Checks what applicant-tracking systems commonly struggle with (tables, text boxes, columns, contact info in
headers, images, missing standard headings) and how well the resume's wording covers a job description.
"""
from __future__ import annotations

import re

from .skills import (ACTION_VERBS, WEAK_STARTS, contains_keyword, expand_implied, find_skills, jd_keywords,
                     role_category, title_tokens)

DISCLAIMER = ("ATS compatibility estimate based on common applicant-tracking-system behaviour. "
              "Real ATS software differs by vendor; no tool can guarantee a pass.")
REQUIRED_SECTIONS = ["summary", "experience", "skills", "education"]
NICE_SECTIONS = ["certifications", "projects"]
PRONOUN_RE = re.compile(r"\b(i|me|my|we|our)\b", re.I)


def _bullets(parsed: dict) -> list[str]:
    out = []
    for e in parsed.get("experience", []):
        out += e.get("responsibilities", [])
    for p in parsed.get("projects", []):
        out += p.get("bullets", [])
    return out


def formatting_issues(info: dict, parsed: dict, raw_text: str) -> list[dict]:
    issues = []

    def add(severity, issue, fix):
        issues.append({"severity": severity, "issue": issue, "fix": fix})

    if info.get("tables"):
        add("high", f"{info['tables']} table(s) found. Many ATS read tables out of order or skip them.",
            "Put content in normal paragraphs and bullet points.")
    if info.get("text_boxes"):
        add("high", "Text boxes found. ATS often ignore text inside text boxes.", "Move that text into the main body.")
    if info.get("columns"):
        add("medium", "Multi-column layout. ATS may mix lines from the two columns.", "Use a single-column layout.")
    if info.get("images"):
        add("medium", f"{info['images']} image(s)/icon(s)/photo found. ATS cannot read them.",
            "Remove photos, icons and skill bars; write the information as text.")
    if info.get("header_has_contact"):
        add("high", "Contact details are inside the page header. Some ATS ignore headers/footers.",
            "Put name, phone and email in the first lines of the body.")
    if info.get("likely_scanned"):
        add("high", "PDF looks scanned (image-only); an ATS will read almost no text.", "Export a text-based PDF from Word.")
    if info.get("file_type") == "pdf" and info.get("pages", 1) > 2:
        add("low", f"{info['pages']} pages. For ~3-5 years of experience, 1-2 pages is standard.", "Trim older/irrelevant detail.")
    if re.search(r"[☀-➿\U0001F300-\U0001FAFF]", raw_text):
        add("low", "Emoji/symbol characters found; some ATS turn them into garbage.", "Remove decorative symbols.")
    if not parsed.get("contact", {}).get("email"):
        add("high", "No email address found.", "Add your email near the top.")
    if not parsed.get("contact", {}).get("phone"):
        add("medium", "No phone number found.", "Add a phone number near the top.")
    return issues


def section_issues(parsed: dict) -> tuple[int, list[str]]:
    found = set(parsed.get("sections_found", []))
    if parsed.get("summary"):
        found.add("summary")
    issues = [f"Missing a clear '{s.title()}' section heading." for s in REQUIRED_SECTIONS if s not in found]
    issues += [f"Optional: add a '{s.title()}' section if you have any." for s in NICE_SECTIONS if s not in found]
    exp = parsed.get("experience", [])
    if exp and any(not e.get("duration") for e in exp):
        issues.append("Some roles have no dates. ATS and recruiters use dates to calculate experience.")
    if exp and any(not e.get("designation") for e in exp):
        issues.append("Some roles have no recognisable job title.")
    if len(parsed.get("skills", [])) < 6:
        issues.append("Skills section is thin. List the tools you actually use (Excel functions, BI tools, SQL).")
    score = round(100 * sum(1 for s in REQUIRED_SECTIONS if s in found) / len(REQUIRED_SECTIONS))
    return score, issues


def readability_issues(parsed: dict, raw_text: str) -> tuple[int, list[str]]:
    bullets = _bullets(parsed)
    issues = []
    if not bullets:
        return 40, ["No bullet points detected under experience. Use short bullets starting with a verb."]
    long = [b for b in bullets if len(b.split()) > 32]
    weak = [b for b in bullets if any(b.lower().startswith(w) for w in WEAK_STARTS)]
    no_verb = [b for b in bullets if b.split() and b.split()[0].lower().strip(",.") not in ACTION_VERBS
               and not any(b.lower().startswith(w) for w in WEAK_STARTS)]
    numbered = [b for b in bullets if re.search(r"\d", b)]
    pronouns = [b for b in bullets if PRONOUN_RE.search(b)]
    if long:
        issues.append(f"{len(long)} bullet(s) are longer than 32 words. Split them.")
    if weak:
        issues.append(f"{len(weak)} bullet(s) start with weak phrases like 'Responsible for'. Start with what you did.")
    if len(no_verb) > len(bullets) / 3:
        issues.append("Many bullets don't start with an action verb (Prepared, Automated, Built...).")
    if len(numbered) < len(bullets) / 4:
        issues.append("Few bullets have numbers. Add real figures you can back up (reports/day, hours saved, users).")
    if pronouns:
        issues.append(f"{len(pronouns)} bullet(s) use I/my/we. Resumes are usually written without pronouns.")
    words = parsed.get("word_count") or len(raw_text.split())
    if words > 900:
        issues.append(f"{words} words is long; aim for roughly 400-750.")
    elif words < 200:
        issues.append(f"Only {words} words; the resume may be too thin to match JDs.")
    score = 100 - 12 * len(issues)
    return max(20, score), issues


def keyword_analysis(jd_text: str, resume_text: str, parsed: dict) -> dict:
    keywords = jd_keywords(jd_text, limit=30)
    res_skills = expand_implied(set(parsed.get("skills", [])) | find_skills(resume_text))
    relevant, missing = [], []
    for k in keywords:
        (relevant if (k in res_skills or contains_keyword(resume_text, k)) else missing).append(k)
    jd_skills = find_skills(jd_text)
    present = sorted(s for s in jd_skills if s in res_skills)
    missing_skills = sorted(s for s in jd_skills if s not in res_skills)
    requirements = _requirements(jd_text)
    coverage = round(100 * len(relevant) / len(keywords)) if keywords else 0
    skill_cov = round(100 * len(present) / len(jd_skills)) if jd_skills else 0
    return {"keyword_coverage": coverage, "skill_coverage": skill_cov, "relevant_keywords": relevant,
            "missing_keywords": missing, "skills_present": present, "missing_skills": missing_skills,
            "important_requirements": requirements}


def _requirements(jd: str) -> list[str]:
    lines = [l.strip(" -•*\t") for l in (jd or "").splitlines()]
    req = [l for l in lines if 6 <= len(l.split()) <= 40 and re.search(
        r"\b(must|required|mandatory|should have|need|minimum|proficien|experience (in|with)|knowledge of|"
        r"strong|expert|hands-on)\b", l, re.I)]
    if not req:  # descriptions without line breaks
        req = [s.strip() for s in re.split(r"(?<=[.;])\s+", jd or "") if re.search(
            r"\b(must|required|mandatory|should have|minimum|proficien|experience (in|with)|knowledge of)\b", s, re.I)
            and 5 <= len(s.split()) <= 40]
    return req[:10]


def experience_relevance(parsed: dict, jd_text: str) -> int:
    jd_sk = find_skills(jd_text)
    bullets = _bullets(parsed)
    if not jd_sk or not bullets:
        return 50
    hit = sum(1 for b in bullets if find_skills(b) & jd_sk)
    return min(100, round(100 * hit / max(1, len(bullets)) * 1.4))


def title_relevance(parsed: dict, job_title: str) -> int:
    if not job_title:
        return 50
    cat = role_category(job_title)
    titles = [e.get("designation", "") for e in parsed.get("experience", [])]
    if cat != "Other" and any(role_category(t) == cat for t in titles):
        return 100
    jt = title_tokens(job_title)
    best = max((len(jt & title_tokens(t)) / len(jt) for t in titles if t and jt), default=0)
    return round(40 + 60 * best) if titles else 40


def analyze(parsed: dict, raw_text: str, format_info: dict, jd_text: str = "", job_title: str = "") -> dict:
    fmt_issues = formatting_issues(format_info or {}, parsed, raw_text)
    penalty = sum({"high": 20, "medium": 10, "low": 4}[i["severity"]] for i in fmt_issues)
    formatting = max(0, 100 - penalty)
    section_score, sec_issues = section_issues(parsed)
    read_score, read_issues = readability_issues(parsed, raw_text)

    result = {
        "formatting_compatibility": formatting, "section_completeness": section_score, "readability": read_score,
        "formatting_issues": fmt_issues, "section_issues": sec_issues, "readability_issues": read_issues,
        "parsing_problems": [i["issue"] for i in fmt_issues if i["severity"] == "high"],
        "parsed_preview": {"name": parsed.get("name"), "contact": parsed.get("contact"),
                           "roles": [f"{e.get('designation')} - {e.get('company')} ({e.get('duration')})"
                                     for e in parsed.get("experience", [])],
                           "skills": parsed.get("skills", [])[:30],
                           "total_experience_years": parsed.get("total_experience_years")},
        "disclaimer": DISCLAIMER,
    }
    if jd_text:
        kw = keyword_analysis(jd_text, raw_text, parsed)
        exp_rel = experience_relevance(parsed, jd_text)
        title_rel = title_relevance(parsed, job_title)
        result.update(kw)
        result.update({"experience_relevance": exp_rel, "job_title_relevance": title_rel})
        score = (0.30 * kw["keyword_coverage"] + 0.20 * kw["skill_coverage"] + 0.15 * exp_rel + 0.10 * title_rel
                 + 0.15 * formatting + 0.05 * section_score + 0.05 * read_score)
    else:
        score = 0.45 * formatting + 0.30 * section_score + 0.25 * read_score
    result["ats_score"] = round(score)
    result["label"] = "ATS compatibility estimate"
    return result
