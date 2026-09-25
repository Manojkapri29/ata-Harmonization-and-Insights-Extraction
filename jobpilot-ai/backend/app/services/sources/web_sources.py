"""Feeds, single-URL import, browser-assisted boards and the demo source."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from urllib.parse import quote, quote_plus, urlparse

from ..normalize import RawJob, clean_html
from .base import PoliteClient, SearchQuery, SourceAdapter, SourceError, register

# ---------------------------------------------------------------- schema.org JobPosting (JSON-LD)

_LD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def _walk(node):
    if isinstance(node, list):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "item", "mainEntity"):
            if key in node:
                yield from _walk(node[key])


def _is_posting(node: dict) -> bool:
    t = node.get("@type")
    return t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t)


def _text(v) -> str:
    if isinstance(v, dict):
        return str(v.get("name") or v.get("value") or v.get("@value") or "")
    if isinstance(v, list):
        return ", ".join(_text(x) for x in v if _text(x))
    return str(v or "")


def jobposting_to_raw(p: dict, source: str, fallback_url: str = "") -> RawJob:
    locs = p.get("jobLocation") or []
    locs = locs if isinstance(locs, list) else [locs]
    places = []
    for loc in locs:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, str):
            places.append(addr)
            continue
        parts = [addr.get("addressLocality"), addr.get("addressRegion"), _text(addr.get("addressCountry"))]
        places.append(", ".join(x for x in parts if x))
    remote = True if str(p.get("jobLocationType", "")).upper() == "TELECOMMUTE" else None
    if remote and not places:
        places = ["Remote"]

    sal = p.get("baseSalary") or p.get("estimatedSalary") or {}
    sal = sal[0] if isinstance(sal, list) and sal else sal
    val = (sal or {}).get("value") or {} if isinstance(sal, dict) else {}
    lo = hi = None
    period = ""
    if isinstance(val, dict):
        lo = val.get("minValue") or val.get("value")
        hi = val.get("maxValue") or val.get("value")
        period = {"YEAR": "year", "MONTH": "month", "HOUR": "hour"}.get(str(val.get("unitText", "")).upper(), "")
    elif isinstance(val, (int, float)):
        lo = hi = val

    exp = p.get("experienceRequirements")
    exp_text = ""
    if isinstance(exp, dict) and exp.get("monthsOfExperience"):
        exp_text = f"{float(exp['monthsOfExperience']) / 12:g}+ years"
    elif exp:
        exp_text = _text(exp)

    org = p.get("hiringOrganization") or {}
    ident = p.get("identifier")
    ident = _text(ident) if ident else ""
    skills = p.get("skills") or []
    skills = [s.strip() for s in (skills.split(",") if isinstance(skills, str) else [_text(s) for s in skills]) if s.strip()]
    return RawJob(
        source=source, source_job_id=ident or p.get("url") or fallback_url, title=_text(p.get("title")),
        company=_text(org) if isinstance(org, dict) else str(org), location=" | ".join(places),
        job_url=p.get("url") or fallback_url, description=str(p.get("description") or ""), posted=p.get("datePosted"),
        salary_min=float(lo) if lo else None, salary_max=float(hi) if hi else None,
        salary_currency=str((sal or {}).get("currency", "")) if isinstance(sal, dict) else "", salary_period=period,
        experience_text=exp_text, employment_type=_text(p.get("employmentType")).replace("_", "-").title(),
        remote=remote, skills=skills, education=_text(p.get("educationRequirements"))[:300],
        company_website=(org.get("sameAs") or org.get("url") or "") if isinstance(org, dict) else "",
    )


def extract_jobpostings(html_or_ld: str | list, source: str, url: str = "") -> list[RawJob]:
    blocks = _LD_RE.findall(html_or_ld) if isinstance(html_or_ld, str) else html_or_ld
    jobs = []
    for block in blocks:
        try:
            data = json.loads(block.strip()) if isinstance(block, str) else block
        except json.JSONDecodeError:
            continue
        jobs += [jobposting_to_raw(n, source, url) for n in _walk(data) if _is_posting(n)]
    return [j for j in jobs if j.title]


def import_from_page(url: str, title: str = "", text: str = "", jsonld: list | None = None,
                     company: str = "", location: str = "") -> list[RawJob]:
    """Page data sent by the browser bookmarklet or pasted by the user (the user is viewing the page)."""
    source = source_for_url(url)
    jobs = extract_jobpostings(jsonld or [], source, url) if jsonld else []
    if jobs:
        return jobs
    if not (title or text):
        raise SourceError("Nothing to import: no JobPosting data and no text.")
    return [RawJob(source=source, title=_guess_title(title), company=company, location=location,
                   job_url=url, description=text[:30000])]


def import_from_url(url: str, http: PoliteClient) -> list[RawJob]:
    """Fetch one public job page (robots.txt respected) and read its schema.org JobPosting."""
    r = http.get(url, check_robots=True)
    jobs = extract_jobpostings(r.text, source_for_url(url), url)
    if jobs:
        return jobs
    m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
    body = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
    text = clean_html(body)
    if len(text) < 200:
        raise SourceError("The page had no readable job details (it may need login or JavaScript). "
                          "Open it in your browser and use the bookmarklet or paste the description.")
    return [RawJob(source=source_for_url(url), title=_guess_title(m.group(1) if m else ""), job_url=url,
                   description=text[:30000])]


def _guess_title(page_title: str) -> str:
    t = clean_html(page_title)
    return re.split(r"\s[|\-–]\s", t)[0].strip()[:300] or "Imported job"


DOMAIN_SOURCES = {"linkedin.com": "linkedin", "naukri.com": "naukri", "indeed.": "indeed", "glassdoor.": "glassdoor",
                  "foundit.": "foundit", "monsterindia.": "foundit", "internshala.com": "internshala",
                  "greenhouse.io": "greenhouse", "lever.co": "lever", "ashbyhq.com": "ashby"}


def source_for_url(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    for dom, key in DOMAIN_SOURCES.items():
        if dom in host:
            return key
    return "url_import" if host else "manual"


# ---------------------------------------------------------------- RSS / Atom feeds

def parse_feed(xml_text: str, source: str = "rss") -> list[RawJob]:
    root = ET.fromstring(xml_text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//a:entry", ns)
    jobs = []
    for it in items:
        def g(tag):
            el = it.find(tag) if not tag.startswith("a:") else it.find(tag, ns)
            return (el.text or "").strip() if el is not None and el.text else ""
        link = g("link")
        if not link:
            el = it.find("a:link", ns)
            link = el.get("href", "") if el is not None else ""
        title = g("title") or g("a:title")
        company = ""
        m = re.match(r"(.+?)\s+(?:at|@)\s+(.+)$", title)
        if m:
            title, company = m.group(1), m.group(2)
        jobs.append(RawJob(source=source, source_job_id=g("guid") or g("a:id") or link, title=title, company=company,
                           job_url=link, description=g("description") or g("a:summary") or g("a:content"),
                           posted=_rss_date(g("pubDate") or g("a:updated") or g("a:published")),
                           location=g("location")))
    return jobs


def _rss_date(s: str):
    from email.utils import parsedate_to_datetime
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).date()
    except (TypeError, ValueError):
        return s[:10]


@register
class RSSSource(SourceAdapter):
    key, name, kind = "rss", "RSS / Atom job feeds", "feed"
    description = "Any public job feed URL (company careers feeds, job-board alert feeds, Google Alerts RSS)."
    config_fields = [{"name": "feeds", "label": "Feed URLs (comma-separated)", "placeholder": "https://.../jobs.rss"}]

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        feeds = [f.strip() for f in str(q.options.get(self.key, {}).get("feeds", "")).split(",") if f.strip()]
        jobs: list[RawJob] = []
        for url in feeds:
            jobs += parse_feed(http.get(url, check_robots=True).text)
        return jobs


# ---------------------------------------------------------------- browser-assisted boards

class AssistedSource(SourceAdapter):
    """Boards whose terms forbid automated scraping or that require login.

    JobPilot never logs in or scrapes these. It builds the search link for you; you open it in your own
    browser and import jobs you like with the bookmarklet, a pasted URL, or the paste-JD form."""
    kind = "assisted"
    supports_search = False
    default_enabled = True
    url_template = ""

    def search(self, q, http):  # pragma: no cover
        return []

    def build(self, kw: str, loc: str, days: int, exp: float | None) -> str:
        raise NotImplementedError

    def search_links(self, q: SearchQuery) -> list[dict]:
        """One link per keyword for the main location, plus one remote link per keyword when wanted."""
        places = [l for l in q.locations if l.lower() != "remote"][:1] or [""]
        if q.include_remote or any(l.lower() == "remote" for l in q.locations):
            places.append("Remote")
        return [{"source": self.key, "board": self.name, "label": f"{kw}{' - ' + loc if loc else ''}",
                 "url": self.build(kw, loc, q.posted_within_days, q.experience_min)}
                for kw in q.keywords[:6] for loc in places]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


@register
class LinkedInSource(AssistedSource):
    key, name = "linkedin", "LinkedIn"
    description = "Browser-assisted. LinkedIn's terms prohibit scraping, so JobPilot opens searches in your browser."
    terms_note = "No scraping, no stored password. Open the link, then import jobs with the bookmarklet."

    def build(self, kw, loc, days, exp):
        url = f"https://www.linkedin.com/jobs/search/?keywords={quote(kw)}&f_TPR=r{days * 86400}"
        if loc and loc.lower() != "remote":
            url += f"&location={quote(loc + ', India')}"
        if loc.lower() == "remote":
            url += "&f_WT=2&location=India"
        return url


@register
class NaukriSource(AssistedSource):
    key, name = "naukri", "Naukri"
    description = "Browser-assisted. Naukri blocks automated access, so searches open in your browser."

    def build(self, kw, loc, days, exp):
        url = f"https://www.naukri.com/{_slug(kw)}-jobs"
        if loc and loc.lower() != "remote":
            url += f"-in-{_slug(loc)}"
        params = [f"jobAge={days}"]
        if exp is not None:
            params.append(f"experience={int(exp)}")
        if loc.lower() == "remote":
            params.append("wfhType=2")
        return url + "?" + "&".join(params)


@register
class IndeedSource(AssistedSource):
    key, name = "indeed", "Indeed India"
    description = "Browser-assisted. Indeed has no public job-search API and blocks bots."

    def build(self, kw, loc, days, exp):
        loc_q = "remote" if loc.lower() == "remote" else loc
        return f"https://in.indeed.com/jobs?q={quote_plus(kw)}&l={quote_plus(loc_q)}&fromage={min(days, 14)}"


@register
class GlassdoorSource(AssistedSource):
    key, name = "glassdoor", "Glassdoor"
    description = "Browser-assisted. Glassdoor requires login for most listings."

    def build(self, kw, loc, days, exp):
        return f"https://www.glassdoor.co.in/Job/jobs.htm?sc.keyword={quote(kw)}&locKeyword={quote(loc)}&fromAge={days}"


@register
class FounditSource(AssistedSource):
    key, name = "foundit", "Foundit (Monster India)"
    description = "Browser-assisted search links."

    def build(self, kw, loc, days, exp):
        url = f"https://www.foundit.in/srp/results?query={quote(kw)}"
        if loc and loc.lower() != "remote":
            url += f"&locations={quote(loc)}"
        if exp is not None:
            url += f"&experienceRanges={int(exp)}~{int(exp) + 2}"
        return url


@register
class InternshalaSource(AssistedSource):
    key, name = "internshala", "Internshala"
    description = "Browser-assisted search links (fresher / early-career jobs)."

    def build(self, kw, loc, days, exp):
        if loc and loc.lower() != "remote":
            return f"https://internshala.com/jobs/{_slug(kw)}-jobs-in-{_slug(loc)}/"
        return f"https://internshala.com/jobs/work-from-home-{_slug(kw)}-jobs/" if loc.lower() == "remote" \
            else f"https://internshala.com/jobs/keywords-{_slug(kw)}/"


# ---------------------------------------------------------------- demo

DEMO_JOBS = [
    ("MIS Executive", "Demo Retail Co.", "Noida, Uttar Pradesh", "3-5 years", "₹4.5-6 LPA",
     "We need an MIS Executive to prepare daily and monthly MIS reports for store operations. Must have Advanced Excel "
     "(VLOOKUP, pivot tables, Power Query), VBA macros for reporting automation and strong data validation skills. "
     "Retail MIS experience preferred. Graduate/MBA. Immediate joiners preferred."),
    ("Data Analyst", "Demo Fintech Pvt Ltd", "Gurugram, Haryana", "2-5 years", "₹6-9 LPA",
     "Analyse transaction data with SQL and Python, build Power BI dashboards with DAX, and present insights to "
     "stakeholders. Experience with data validation, KPI tracking and management reporting. Any graduate; MBA a plus."),
    ("Business Intelligence Analyst", "Demo Logistics", "Remote (India)", "3-6 years", "",
     "Own Power BI and Tableau dashboards, write complex SQL, design data models and automate reporting. "
     "ETL knowledge and stakeholder management required. Supply chain domain is a plus."),
    ("Reporting Analyst", "Demo Hospitality Group", "New Delhi", "3+ years", "₹40,000 - 55,000 per month",
     "Prepare management reports and dashboards in Advanced Excel and Power BI. Reconcile data across systems, "
     "ensure data accuracy, and automate recurring reports with Power Query and macros. Hospitality experience preferred."),
    ("Senior Data Engineer", "Demo Cloud Inc", "Bengaluru", "6-10 years", "₹25-35 LPA",
     "Build Spark and Airflow pipelines on AWS, Kafka streaming, Scala. B.Tech in Computer Science required."),
]


@register
class DemoSource(SourceAdapter):
    key, name, kind = "demo", "Demo data (sample jobs)", "demo"
    description = "Five clearly-labelled FAKE sample jobs for trying the app offline. Disable for real use."
    default_enabled = False

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        today = date.today()
        return [RawJob(source="demo", source_job_id=f"demo-{i}", title=t, company=c, location=l,
                       experience_text=e, salary_text=s, description=f"[SAMPLE JOB - NOT REAL]\n\n{d}",
                       job_url=f"https://example.com/demo-job/{i}", posted=today - timedelta(days=i))
                for i, (t, c, l, e, s, d) in enumerate(DEMO_JOBS, start=1)]
