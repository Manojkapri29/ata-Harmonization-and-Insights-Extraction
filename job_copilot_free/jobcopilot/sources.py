"""Job sources.

Every source is free. Most are official public JSON APIs (no scraping, no login).
Each source has a pure ``parse_*`` function (JSON -> list[Job]) so it can be
tested offline, and a ``fetch_*`` function that does the HTTP call.

Sources:
    remotive, arbeitnow, remoteok, themuse   -> free, no key
    greenhouse, lever, ashby                  -> free company career-page APIs (no key)
    adzuna                                    -> free API key (supports India: country "in")
    jobspy                                    -> optional; scrapes LinkedIn/Indeed/Naukri/Glassdoor.
                                                 Unofficial, may break or get rate-limited.
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable

import requests

USER_AGENT = "Mozilla/5.0 (compatible; FreeJobCopilot/1.0; personal job search)"
TIMEOUT = 20


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str
    posted: str = ""
    remote: bool | None = None
    salary: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        raw = f"{self.title.strip().lower()}|{self.company.strip().lower()}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tags"] = ", ".join(self.tags)
        d["key"] = self.key
        return d


# ---------------------------------------------------------------- helpers

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_html(text: str | None) -> str:
    """HTML (possibly entity-escaped, as Greenhouse sends it) -> plain text."""
    if not text:
        return ""
    text = html.unescape(html.unescape(text))
    text = re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>", "\n", text, flags=re.I)
    text = _TAG_RE.sub(" ", text)
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _date(value) -> str:
    """Accept ISO strings, unix seconds or unix milliseconds; return YYYY-MM-DD."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        if value > 1e12:  # milliseconds
            value /= 1000
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
    return str(value)[:10]


def _salary(lo, hi, currency: str = "") -> str:
    if not lo and not hi:
        return ""
    cur = f"{currency} " if currency else ""
    if lo and hi:
        return f"{cur}{int(lo):,} - {int(hi):,}"
    return f"{cur}{int(lo or hi):,}"


def _get(url: str, params: dict | None = None):
    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def matches_query(job: Job, query: str) -> bool:
    """Comma-separated phrases; a job matches if ANY phrase is in its title or tags,
    or ALL words of a phrase appear in the description."""
    phrases = [p.strip().lower() for p in query.split(",") if p.strip()]
    if not phrases:
        return True
    head = f"{job.title} {' '.join(job.tags)}".lower()
    body = job.description.lower()
    for p in phrases:
        if p in head:
            return True
        words = p.split()
        if len(words) > 1 and all(re.search(rf"\b{re.escape(w)}\b", body) for w in words):
            return True
    return False


REMOTE_WORDS = ("remote", "anywhere", "worldwide", "work from home", "wfh")


def matches_location(job: Job, location: str, include_remote: bool = True) -> bool:
    if not location.strip():
        return True
    loc = job.location.lower()
    if include_remote and (job.remote or any(w in loc for w in REMOTE_WORDS)):
        return True
    return any(part.strip().lower() in loc for part in location.split(",") if part.strip())


# ---------------------------------------------------------------- parsers (pure)

def parse_remotive(payload: dict) -> list[Job]:
    return [
        Job(
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            location=j.get("candidate_required_location") or "Remote",
            url=j.get("url", ""),
            description=clean_html(j.get("description")),
            source="Remotive",
            posted=_date(j.get("publication_date")),
            remote=True,
            salary=j.get("salary") or "",
            tags=list(j.get("tags") or []),
        )
        for j in payload.get("jobs", [])
    ]


def parse_arbeitnow(payload: dict) -> list[Job]:
    return [
        Job(
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            location=j.get("location") or ("Remote" if j.get("remote") else ""),
            url=j.get("url", ""),
            description=clean_html(j.get("description")),
            source="Arbeitnow",
            posted=_date(j.get("created_at")),
            remote=bool(j.get("remote")),
            tags=list(j.get("tags") or []),
        )
        for j in payload.get("data", [])
    ]


def parse_remoteok(payload: list) -> list[Job]:
    jobs = []
    for j in payload:
        if not isinstance(j, dict) or "position" not in j:  # first item is a legal notice
            continue
        jobs.append(
            Job(
                title=j.get("position", ""),
                company=j.get("company", ""),
                location=j.get("location") or "Remote",
                url=j.get("url") or j.get("apply_url", ""),
                description=clean_html(j.get("description")),
                source="RemoteOK",
                posted=_date(j.get("date")),
                remote=True,
                salary=_salary(j.get("salary_min"), j.get("salary_max"), "USD"),
                tags=list(j.get("tags") or []),
            )
        )
    return jobs


def parse_themuse(payload: dict) -> list[Job]:
    jobs = []
    for j in payload.get("results", []):
        locs = ", ".join(l.get("name", "") for l in j.get("locations", []))
        jobs.append(
            Job(
                title=j.get("name", ""),
                company=(j.get("company") or {}).get("name", ""),
                location=locs,
                url=(j.get("refs") or {}).get("landing_page", ""),
                description=clean_html(j.get("contents")),
                source="The Muse",
                posted=_date(j.get("publication_date")),
                remote="remote" in locs.lower() or "flexible" in locs.lower(),
                tags=[c.get("name", "") for c in j.get("categories", [])],
            )
        )
    return jobs


def parse_greenhouse(payload: dict, company: str) -> list[Job]:
    return [
        Job(
            title=j.get("title", ""),
            company=company,
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            description=clean_html(j.get("content")),
            source="Greenhouse",
            posted=_date(j.get("updated_at")),
        )
        for j in payload.get("jobs", [])
    ]


def parse_lever(payload: list, company: str) -> list[Job]:
    jobs = []
    for j in payload:
        cats = j.get("categories") or {}
        desc = j.get("descriptionPlain") or clean_html(j.get("description"))
        for block in j.get("lists", []):
            desc += f"\n{block.get('text', '')}\n{clean_html(block.get('content'))}"
        jobs.append(
            Job(
                title=j.get("text", ""),
                company=company,
                location=cats.get("location", ""),
                url=j.get("hostedUrl", ""),
                description=desc.strip(),
                source="Lever",
                posted=_date(j.get("createdAt")),
                remote=(j.get("workplaceType") == "remote") or None,
                tags=[t for t in (cats.get("team"), cats.get("commitment")) if t],
            )
        )
    return jobs


def parse_ashby(payload: dict, company: str) -> list[Job]:
    return [
        Job(
            title=j.get("title", ""),
            company=company,
            location=j.get("location", ""),
            url=j.get("jobUrl") or j.get("applyUrl", ""),
            description=j.get("descriptionPlain") or clean_html(j.get("descriptionHtml")),
            source="Ashby",
            posted=_date(j.get("publishedAt")),
            remote=j.get("isRemote"),
            tags=[t for t in (j.get("department"), j.get("employmentType")) if t],
        )
        for j in payload.get("jobs", [])
    ]


def parse_adzuna(payload: dict) -> list[Job]:
    return [
        Job(
            title=clean_html(j.get("title")),
            company=(j.get("company") or {}).get("display_name", ""),
            location=(j.get("location") or {}).get("display_name", ""),
            url=j.get("redirect_url", ""),
            description=clean_html(j.get("description")),
            source="Adzuna",
            posted=_date(j.get("created")),
            salary=_salary(j.get("salary_min"), j.get("salary_max")),
        )
        for j in payload.get("results", [])
    ]


def parse_jobspy(df) -> list[Job]:
    jobs = []
    for row in df.fillna("").to_dict("records"):
        jobs.append(
            Job(
                title=str(row.get("title", "")),
                company=str(row.get("company", "")),
                location=str(row.get("location", "")),
                url=str(row.get("job_url_direct") or row.get("job_url", "")),
                description=str(row.get("description", "")),
                source=f"JobSpy/{row.get('site', '')}",
                posted=_date(str(row.get("date_posted", ""))),
                remote=bool(row.get("is_remote")) if row.get("is_remote") != "" else None,
                salary=_salary(row.get("min_amount"), row.get("max_amount"), str(row.get("currency", ""))),
                tags=[s.strip() for s in str(row.get("skills", "")).split(",") if s.strip()],
            )
        )
    return jobs


# ---------------------------------------------------------------- fetchers (network)

def fetch_remotive(query: str, **_) -> list[Job]:
    # Remotive's search is single-term; search the first phrase, filter locally for the rest.
    first = query.split(",")[0].strip()
    return parse_remotive(_get("https://remotive.com/api/remote-jobs", {"search": first, "limit": 200}))


def fetch_arbeitnow(query: str, pages: int = 3, **_) -> list[Job]:
    jobs: list[Job] = []
    for page in range(1, pages + 1):
        jobs += parse_arbeitnow(_get("https://www.arbeitnow.com/api/job-board-api", {"page": page}))
    return jobs


def fetch_remoteok(query: str, **_) -> list[Job]:
    return parse_remoteok(_get("https://remoteok.com/api"))


def fetch_themuse(query: str, location: str = "", pages: int = 3, **_) -> list[Job]:
    jobs: list[Job] = []
    for page in range(pages):
        params = {"page": page, "category": "Data and Analytics"}
        if location:
            params["location"] = location
        jobs += parse_themuse(_get("https://www.themuse.com/api/public/jobs", params))
    return jobs


def _split(names: str) -> list[str]:
    return [n.strip() for n in names.split(",") if n.strip()]


def fetch_greenhouse(query: str, companies: str = "", **_) -> list[Job]:
    jobs: list[Job] = []
    for c in _split(companies):
        jobs += parse_greenhouse(_get(f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs", {"content": "true"}), c)
    return jobs


def fetch_lever(query: str, companies: str = "", **_) -> list[Job]:
    jobs: list[Job] = []
    for c in _split(companies):
        jobs += parse_lever(_get(f"https://api.lever.co/v0/postings/{c}", {"mode": "json"}), c)
    return jobs


def fetch_ashby(query: str, companies: str = "", **_) -> list[Job]:
    jobs: list[Job] = []
    for c in _split(companies):
        jobs += parse_ashby(_get(f"https://api.ashbyhq.com/posting-api/job-board/{c}"), c)
    return jobs


def fetch_adzuna(query: str, location: str = "", app_id: str = "", app_key: str = "",
                 country: str = "in", pages: int = 2, **_) -> list[Job]:
    if not (app_id and app_key):
        raise ValueError("Adzuna needs a free app_id and app_key from https://developer.adzuna.com")
    jobs: list[Job] = []
    for page in range(1, pages + 1):
        params = {"app_id": app_id, "app_key": app_key, "what": query.replace(",", " "),
                  "results_per_page": 50, "content-type": "application/json"}
        if location:
            params["where"] = location
        jobs += parse_adzuna(_get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}", params))
    return jobs


def fetch_jobspy(query: str, location: str = "", sites: str = "indeed,linkedin,naukri",
                 results: int = 30, hours_old: int = 168, country: str = "India", **_) -> list[Job]:
    try:
        from jobspy import scrape_jobs
    except ImportError as e:
        raise ImportError("Optional: pip install python-jobspy") from e
    df = scrape_jobs(
        site_name=_split(sites), search_term=query.replace(",", " OR "),
        location=location or None, results_wanted=results, hours_old=hours_old,
        country_indeed=country, linkedin_fetch_description=True,
    )
    return parse_jobspy(df)


# Sources that search on the server side need no local query filtering.
SERVER_SIDE_SEARCH = {"adzuna", "jobspy"}

SOURCES: dict[str, Callable[..., list[Job]]] = {
    "remotive": fetch_remotive,
    "arbeitnow": fetch_arbeitnow,
    "remoteok": fetch_remoteok,
    "themuse": fetch_themuse,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "adzuna": fetch_adzuna,
    "jobspy": fetch_jobspy,
}


def search(query: str, location: str, sources: list[str], include_remote: bool = True,
           options: dict | None = None) -> tuple[list[Job], dict[str, str]]:
    """Run the chosen sources, filter, de-duplicate.

    Returns (jobs, errors) where errors maps source -> message. One failing
    source never breaks the others.
    """
    options = options or {}
    jobs: list[Job] = []
    errors: dict[str, str] = {}
    for name in sources:
        try:
            found = SOURCES[name](query, location=location, **options.get(name, {}))
        except Exception as e:  # network errors, bad keys, site changes
            errors[name] = f"{type(e).__name__}: {e}"
            continue
        if name not in SERVER_SIDE_SEARCH:
            found = [j for j in found if matches_query(j, query)]
            found = [j for j in found if matches_location(j, location, include_remote)]
        jobs += found

    seen: set[str] = set()
    unique = []
    for j in jobs:
        if j.key not in seen and j.title:
            seen.add(j.key)
            unique.append(j)
    return unique, errors
