"""Official / public JSON job APIs. Each has a pure parse_* function (tested offline) and an adapter."""
from __future__ import annotations

from ..normalize import RawJob, clean_html
from .base import PoliteClient, SearchQuery, SourceAdapter, SourceError, register


def _split(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


# ---------------------------------------------------------------- parsers

def parse_remotive(payload: dict) -> list[RawJob]:
    return [RawJob(source="remotive", source_job_id=str(j.get("id", "")), title=j.get("title", ""),
                   company=j.get("company_name", ""), location=j.get("candidate_required_location") or "Remote",
                   job_url=j.get("url", ""), description=j.get("description", ""), posted=j.get("publication_date"),
                   remote=True, salary_text=j.get("salary") or "", employment_type=(j.get("job_type") or "").replace("_", "-").title(),
                   skills=list(j.get("tags") or []))
            for j in payload.get("jobs", [])]


def parse_arbeitnow(payload: dict) -> list[RawJob]:
    return [RawJob(source="arbeitnow", source_job_id=j.get("slug", ""), title=j.get("title", ""),
                   company=j.get("company_name", ""), location=j.get("location") or "", job_url=j.get("url", ""),
                   description=j.get("description", ""), posted=j.get("created_at"), remote=bool(j.get("remote")),
                   employment_type=", ".join(j.get("job_types") or []))
            for j in payload.get("data", [])]


def parse_remoteok(payload: list) -> list[RawJob]:
    out = []
    for j in payload:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first element is RemoteOK's legal notice
        out.append(RawJob(source="remoteok", source_job_id=str(j.get("id", "")), title=j.get("position", ""),
                          company=j.get("company", ""), location=j.get("location") or "Remote",
                          job_url=j.get("url") or "", application_url=j.get("apply_url") or "",
                          description=j.get("description", ""), posted=j.get("date"), remote=True,
                          salary_min=j.get("salary_min") or None, salary_max=j.get("salary_max") or None,
                          salary_currency="USD" if j.get("salary_min") else "", salary_period="year",
                          skills=list(j.get("tags") or [])))
    return out


def parse_themuse(payload: dict) -> list[RawJob]:
    out = []
    for j in payload.get("results", []):
        locs = ", ".join(l.get("name", "") for l in j.get("locations", []))
        out.append(RawJob(source="themuse", source_job_id=str(j.get("id", "")), title=j.get("name", ""),
                          company=(j.get("company") or {}).get("name", ""), location=locs,
                          job_url=(j.get("refs") or {}).get("landing_page", ""), description=j.get("contents", ""),
                          posted=j.get("publication_date"),
                          remote=("remote" in locs.lower() or "flexible" in locs.lower()) or None))
    return out


def parse_greenhouse(payload: dict, company: str) -> list[RawJob]:
    return [RawJob(source="greenhouse", source_job_id=f"{company}:{j.get('id', '')}", title=j.get("title", ""),
                   company=company, location=(j.get("location") or {}).get("name", ""), job_url=j.get("absolute_url", ""),
                   description=j.get("content", ""), posted=j.get("updated_at"))
            for j in payload.get("jobs", [])]


def parse_lever(payload: list, company: str) -> list[RawJob]:
    out = []
    for j in payload:
        cats = j.get("categories") or {}
        desc = j.get("descriptionPlain") or clean_html(j.get("description"))
        for block in j.get("lists", []):
            desc += f"\n\n{block.get('text', '')}\n{clean_html(block.get('content'))}"
        sal = j.get("salaryRange") or {}
        out.append(RawJob(source="lever", source_job_id=f"{company}:{j.get('id', '')}", title=j.get("text", ""),
                          company=company, location=cats.get("location", ""), job_url=j.get("hostedUrl", ""),
                          application_url=j.get("applyUrl", ""), description=desc, posted=j.get("createdAt"),
                          employment_type=cats.get("commitment", ""),
                          remote=True if j.get("workplaceType") == "remote" else None,
                          salary_min=sal.get("min"), salary_max=sal.get("max"), salary_currency=sal.get("currency", ""),
                          salary_period={"per-year-salary": "year", "per-month-salary": "month",
                                         "per-hour-wage": "hour"}.get(sal.get("interval", ""), "")))
    return out


def parse_ashby(payload: dict, company: str) -> list[RawJob]:
    return [RawJob(source="ashby", source_job_id=f"{company}:{j.get('id') or j.get('jobUrl', '')}", title=j.get("title", ""),
                   company=company, location=j.get("location", ""), job_url=j.get("jobUrl", ""),
                   application_url=j.get("applyUrl", ""),
                   description=j.get("descriptionPlain") or j.get("descriptionHtml", ""), posted=j.get("publishedAt"),
                   remote=j.get("isRemote"), employment_type=j.get("employmentType", ""))
            for j in payload.get("jobs", [])]


def parse_adzuna(payload: dict) -> list[RawJob]:
    return [RawJob(source="adzuna", source_job_id=str(j.get("id", "")), title=j.get("title", ""),
                   company=(j.get("company") or {}).get("display_name", ""),
                   location=(j.get("location") or {}).get("display_name", ""), job_url=j.get("redirect_url", ""),
                   description=j.get("description", ""), posted=j.get("created"),
                   salary_min=j.get("salary_min"), salary_max=j.get("salary_max"), salary_period="year",
                   employment_type={"full_time": "Full-time", "part_time": "Part-time"}.get(j.get("contract_time", ""), ""))
            for j in payload.get("results", [])]


# ---------------------------------------------------------------- adapters

@register
class RemotiveSource(SourceAdapter):
    key, name, kind = "remotive", "Remotive", "api"
    description = "Free public API of remote jobs worldwide. No key needed."
    terms_note = "Public API; Remotive asks you to link back to the original posting (the app always does)."

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        for kw in q.keywords[:5] or [""]:
            jobs += parse_remotive(http.json("https://remotive.com/api/remote-jobs", params={"search": kw, "limit": 100}))
        return jobs


@register
class ArbeitnowSource(SourceAdapter):
    key, name, kind = "arbeitnow", "Arbeitnow", "api"
    description = "Free public job-board API (Europe + remote). No key needed."

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        for page in (1, 2, 3):
            jobs += parse_arbeitnow(http.json("https://www.arbeitnow.com/api/job-board-api", params={"page": page}))
        return jobs


@register
class RemoteOKSource(SourceAdapter):
    key, name, kind = "remoteok", "RemoteOK", "api"
    description = "Free public API of remote jobs. No key needed."
    terms_note = "RemoteOK's API terms require linking back to RemoteOK; job links point there."

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        return parse_remoteok(http.json("https://remoteok.com/api"))


@register
class TheMuseSource(SourceAdapter):
    key, name, kind = "themuse", "The Muse", "api"
    description = "Free public API, 'Data and Analytics' category (mostly US/EU). No key needed."

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        for page in (0, 1, 2):
            jobs += parse_themuse(http.json("https://www.themuse.com/api/public/jobs",
                                            params={"page": page, "category": "Data and Analytics"}))
        return jobs


class _BoardSource(SourceAdapter):
    kind = "company"
    config_fields = [{"name": "companies", "label": "Company board names (comma-separated)",
                      "placeholder": "e.g. razorpay, groww"}]

    def boards(self, q: SearchQuery) -> list[str]:
        return _split(q.options.get(self.key, {}).get("companies", ""))


@register
class GreenhouseSource(_BoardSource):
    key, name = "greenhouse", "Greenhouse career pages"
    description = "Official public job-board API for companies using Greenhouse (boards.greenhouse.io/<name>)."

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        for c in self.boards(q):
            jobs += parse_greenhouse(http.json(f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs",
                                               params={"content": "true"}), c)
        return jobs


@register
class LeverSource(_BoardSource):
    key, name = "lever", "Lever career pages"
    description = "Official public postings API for companies using Lever (jobs.lever.co/<name>)."

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        for c in self.boards(q):
            jobs += parse_lever(http.json(f"https://api.lever.co/v0/postings/{c}", params={"mode": "json"}), c)
        return jobs


@register
class AshbySource(_BoardSource):
    key, name = "ashby", "Ashby career pages"
    description = "Official public job-board API for companies using Ashby (jobs.ashbyhq.com/<name>)."

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        for c in self.boards(q):
            jobs += parse_ashby(http.json(f"https://api.ashbyhq.com/posting-api/job-board/{c}"), c)
        return jobs


@register
class AdzunaSource(SourceAdapter):
    key, name, kind = "adzuna", "Adzuna (India)", "api"
    description = "Official job-search API with good India coverage (aggregates many Indian boards). Free key."
    requires_credentials = ["ADZUNA_APP_ID", "ADZUNA_APP_KEY"]
    server_side_filtering = True
    config_fields = [{"name": "country", "label": "Country code", "placeholder": "in"}]
    terms_note = "Get a free app_id/app_key at https://developer.adzuna.com and put them in backend/.env."

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        from ...config import get_settings
        s = get_settings()
        if not (s.adzuna_app_id and s.adzuna_app_key):
            raise SourceError("Adzuna needs ADZUNA_APP_ID and ADZUNA_APP_KEY in backend/.env (free at developer.adzuna.com)")
        country = q.options.get(self.key, {}).get("country") or "in"
        jobs: list[RawJob] = []
        locations = q.locations or [""]
        for kw in q.keywords[:6]:
            for loc in locations[:4]:
                params = {"app_id": s.adzuna_app_id, "app_key": s.adzuna_app_key, "what_phrase": kw,
                          "results_per_page": 50, "max_days_old": q.posted_within_days, "content-type": "application/json"}
                if loc and loc.lower() != "remote":
                    params["where"] = loc
                jobs += parse_adzuna(http.json(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params=params))
        return jobs
