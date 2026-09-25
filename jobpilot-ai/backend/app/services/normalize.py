"""Turn raw job records from any source into one clean shape, and compute a de-duplication key."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .skills import find_skills, role_category


@dataclass
class RawJob:
    """What a source adapter returns. Only title is mandatory; everything else is best-effort."""
    source: str
    title: str
    company: str = ""
    location: str = ""
    job_url: str = ""
    description: str = ""
    source_job_id: str = ""
    posted: str | int | float | date | None = None
    salary_text: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_period: str = ""            # year | month | hour, when the source says so
    experience_text: str = ""
    employment_type: str = ""
    remote: bool | None = None
    skills: list[str] = field(default_factory=list)
    application_url: str = ""
    company_website: str = ""
    education: str = ""


# ---------------------------------------------------------------- text

_TAG_RE = re.compile(r"<[^>]+>")


def clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(html.unescape(str(text)))
    text = re.sub(r"<\s*(br|/p|/li|/h\d|/div|/tr)\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "\n- ", text, flags=re.I)
    text = _TAG_RE.sub(" ", text)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if not blank and out:
                out.append("")
            blank = True
            continue
        out.append(ln)
        blank = False
    return "\n".join(out).strip()


# ---------------------------------------------------------------- dates

def parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        if value > 1e12:
            value /= 1000
        return datetime.fromtimestamp(value, tz=timezone.utc).date()
    s = str(value).strip().lower()
    today = datetime.now(timezone.utc).date()
    if s in ("today", "just now", "just posted") or "hour" in s or "minute" in s:
        return today
    if s == "yesterday":
        return today - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*(day|week|month)s?\s*ago", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return today - timedelta(days=n * {"day": 1, "week": 7, "month": 30}[unit])
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- salary

_NUM = r"(\d+(?:[.,]\d+)*)"


def _to_number(s: str, unit: str = "") -> float:
    n = float(s.replace(",", ""))
    unit = unit.lower()
    if unit in ("k", "thousand"):
        n *= 1_000
    elif unit in ("l", "lac", "lakh", "lakhs", "lacs", "lpa"):
        n *= 100_000
    elif unit in ("cr", "crore", "crores"):
        n *= 10_000_000
    elif unit in ("m", "mn", "million"):
        n *= 1_000_000
    return n


def parse_salary(text: str) -> tuple[float | None, float | None, str, str]:
    """'₹4-6 LPA' -> (400000, 600000, 'INR', 'year'). Returns (min, max, currency, period); amounts as stated."""
    if not text:
        return None, None, "", ""
    t = text.lower().replace("–", "-").replace("—", "-").replace(" to ", "-")
    if re.search(r"not disclosed|competitive|as per|negotiable|best in", t):
        return None, None, "", ""
    currency = ("INR" if re.search(r"₹|rs\.?|inr|lpa|lakh|lac|crore", t) else
                "USD" if "$" in t or "usd" in t else "EUR" if "€" in t or "eur" in t else
                "GBP" if "£" in t or "gbp" in t else "")
    period = ("month" if re.search(r"per month|/month|/mo\b|monthly|p\.?m\.?\b|a month", t) else
              "hour" if re.search(r"per hour|/hr|/hour|hourly", t) else
              "year" if re.search(r"lpa|per annum|p\.?a\.?\b|/year|/yr|annual|a year|per year", t) else "")
    unit_re = r"\s*(k|thousand|lpa|lakhs?|lacs?|l\b|crores?|cr\b|m\b|mn|million)?"
    m = re.search(_NUM + unit_re + r"\s*-\s*[₹$€£]?\s*(?:rs\.?\s*)?" + _NUM + unit_re, t)
    if m:
        u2 = m.group(4) or ""
        u1 = m.group(2) or u2           # "4-6 LPA": unit written once
        lo, hi = _to_number(m.group(1), u1), _to_number(m.group(3), u2)
    else:
        m = re.search(_NUM + unit_re, t)
        if not m:
            return None, None, currency, period
        lo = hi = _to_number(m.group(1), m.group(2) or "")
    if "lpa" in t and not period:
        period = "year"
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi, currency, period


def annualize(amount: float | None, period: str) -> float | None:
    if amount is None:
        return None
    if period == "month":
        return amount * 12
    if period == "hour":
        return amount * 8 * 22 * 12
    if not period and amount < 200_000 and amount >= 5_000:
        # Indian listings often state monthly CTC without saying so (e.g. "25,000 - 35,000")
        return amount * 12
    return amount


def format_salary(lo: float | None, hi: float | None, currency: str) -> str:
    if lo is None and hi is None:
        return ""
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency, "")

    def fmt(v: float) -> str:
        if currency == "INR" and v >= 100_000:
            return f"{v / 100_000:.1f}".rstrip("0").rstrip(".") + " L"
        return f"{v:,.0f}"
    return f"{sym}{fmt(lo)} - {sym}{fmt(hi)} /yr" if lo != hi else f"{sym}{fmt(lo)} /yr"


# ---------------------------------------------------------------- experience

def parse_experience(text: str) -> tuple[float | None, float | None]:
    """'3-5 years' -> (3, 5); '3+ yrs' -> (3, None); 'minimum 2 years' -> (2, None); 'fresher' -> (0, 1)."""
    if not text:
        return None, None
    t = text.lower().replace("–", "-").replace(" to ", "-")
    if re.search(r"\bfresher|entry[- ]level|no experience\b", t):
        return 0.0, 1.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"(?:minimum|min\.?|at least|atleast)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)", t)
    if m:
        return float(m.group(1)), None
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)", t)
    if m:
        return float(m.group(1)), None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\s*(?:of\s*)?(?:relevant\s*|professional\s*|work\s*)?(?:experience|exp)", t)
    if m:
        return float(m.group(1)), None
    return None, None


# ---------------------------------------------------------------- location

CITY_ALIASES = {
    "gurgaon": "Gurugram", "gurugram": "Gurugram", "new delhi": "Delhi", "delhi": "Delhi", "noida": "Noida",
    "greater noida": "Greater Noida", "ghaziabad": "Ghaziabad", "faridabad": "Faridabad", "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru", "mumbai": "Mumbai", "bombay": "Mumbai", "navi mumbai": "Navi Mumbai",
    "pune": "Pune", "hyderabad": "Hyderabad", "chennai": "Chennai", "kolkata": "Kolkata", "ahmedabad": "Ahmedabad",
    "jaipur": "Jaipur", "chandigarh": "Chandigarh", "mohali": "Mohali", "ludhiana": "Ludhiana", "lucknow": "Lucknow",
    "indore": "Indore", "kochi": "Kochi", "coimbatore": "Coimbatore",
}
NCR = {"Delhi", "Gurugram", "Noida", "Greater Noida", "Ghaziabad", "Faridabad"}
REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|anywhere|worldwide|distributed)\b", re.I)


def cities_in(text: str) -> set[str]:
    t = (text or "").lower()
    found = {canon for alias, canon in CITY_ALIASES.items() if re.search(rf"\b{re.escape(alias)}\b", t)}
    if re.search(r"\b(delhi ncr|ncr|delhi/ncr|delhi-ncr)\b", t):
        found.add("Delhi NCR")
    return found


def normalize_location(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    for alias, canon in (("gurgaon", "Gurugram"), ("bangalore", "Bengaluru"), ("bombay", "Mumbai")):
        text = re.sub(rf"\b{alias}\b", canon, text, flags=re.I)
    return text


def is_india(text: str) -> bool:
    return bool(cities_in(text)) or "india" in (text or "").lower()


# ---------------------------------------------------------------- misc fields

def detect_employment_type(text: str) -> str:
    t = (text or "").lower()
    for label, pat in (("Internship", r"\bintern(ship)?\b"), ("Contract", r"\bcontract(ual)?\b|\btemporary\b"),
                       ("Part-time", r"\bpart[- ]time\b"), ("Full-time", r"\bfull[- ]time\b|\bpermanent\b")):
        if re.search(pat, t):
            return label
    return ""


def detect_education(text: str) -> str:
    t = (text or "").lower()
    found = []
    for label, pat in (("MBA/PGDM", r"\bmba\b|\bpgdm\b|post[- ]graduat"), ("B.Tech/B.E.", r"\bb\.?\s?tech\b|\bb\.?e\.?\b(?= |/|,)"),
                       ("M.Tech/MCA", r"\bm\.?\s?tech\b|\bmca\b"), ("B.Com/BBA", r"\bb\.?\s?com\b|\bbba\b"),
                       ("Any Graduate", r"\bany graduate\b|\bgraduat(e|ion)\b|\bbachelor"), ("Master's", r"\bmaster'?s\b"),
                       ("CA/CFA", r"\bchartered accountant\b|\bcfa\b")):
        if re.search(pat, t):
            found.append(label)
    return ", ".join(found)


def detect_notice_period(text: str) -> str:
    m = re.search(r"(immediate joiners?|immediate(ly)? available|notice period[^.\n]{0,40}|join within [^.\n]{0,20})",
                  text or "", re.I)
    return m.group(0).strip()[:100] if m else ""


# ---------------------------------------------------------------- canonical url / dedupe

TRACKING_PARAMS = re.compile(r"^(utm_|ref|refid|trk|src|source|gclid|fbclid|mc_|campaign)", re.I)


def canonical_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not TRACKING_PARAMS.match(k)])
    return urlunparse((p.scheme.lower() or "https", p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), "", query, ""))


_COMPANY_SUFFIX = re.compile(r"\b(pvt|private|ltd|limited|llp|inc|llc|corp|corporation|co|india|technologies|"
                             r"technology|solutions|services|group)\b\.?", re.I)


def norm_company(name: str) -> str:
    n = _COMPANY_SUFFIX.sub(" ", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def norm_title(title: str) -> str:
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", (title or "").lower())
    t = re.sub(r"\b(sr|senior)\b\.?", "senior", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def dedupe_hash(title: str, company: str, location: str) -> str:
    """Same role at same company in same city = same job, whichever board it came from."""
    city = sorted(cities_in(location))
    loc = city[0] if city else ("remote" if REMOTE_RE.search(location or "") else re.sub(r"[^a-z]+", "", (location or "").lower())[:30])
    key = f"{norm_title(title)}|{norm_company(company)}|{loc}"
    return hashlib.sha1(key.encode()).hexdigest()


# ---------------------------------------------------------------- main entry

def normalize(raw: RawJob) -> dict:
    description = clean_html(raw.description)
    title = clean_html(raw.title).strip()
    company = clean_html(raw.company).strip()
    location = normalize_location(clean_html(raw.location))
    full_text = f"{title}\n{location}\n{raw.salary_text}\n{raw.experience_text}\n{description}"

    remote = raw.remote
    if remote is None and REMOTE_RE.search(f"{title} {location}"):
        remote = True

    lo, hi, cur, period = raw.salary_min, raw.salary_max, raw.salary_currency, raw.salary_period
    if lo is None and hi is None:
        text = raw.salary_text or _salary_snippet(description)
        lo, hi, cur2, period2 = parse_salary(text)
        cur, period = cur or cur2, period or period2
    if cur == "" and (lo or hi) and is_india(location):
        cur = "INR"
    lo, hi = annualize(lo, period), annualize(hi, period)

    exp_min, exp_max = parse_experience(raw.experience_text or "")
    if exp_min is None:
        exp_min, exp_max = parse_experience(f"{title}\n{description}")

    skills = sorted(set(find_skills(full_text)) | {s.strip() for s in raw.skills if s and s.strip()})
    job_url = raw.job_url.strip()
    source_job_id = (raw.source_job_id or canonical_url(job_url) or dedupe_hash(title, company, location))[:300]

    return {
        "source": raw.source,
        "source_job_id": str(source_job_id),
        "job_url": job_url,
        "title": title[:300],
        "company": company[:300],
        "location": location[:300],
        "remote": remote,
        "salary_min": lo,
        "salary_max": hi,
        "salary_currency": cur,
        "salary_text": (raw.salary_text or format_salary(lo, hi, cur))[:200],
        "experience_min": exp_min,
        "experience_max": exp_max,
        "employment_type": raw.employment_type or detect_employment_type(full_text),
        "posted_date": parse_date(raw.posted),
        "description": description,
        "skills": skills,
        "education": (raw.education or detect_education(description))[:300],
        "notice_period": detect_notice_period(description),
        "application_url": raw.application_url or job_url,
        "company_website": raw.company_website,
        "role_category": role_category(title),
        "dedupe_hash": dedupe_hash(title, company, location),
    }


def _salary_snippet(description: str) -> str:
    m = re.search(r"(salary|ctc|compensation|stipend|package|pay)[^\n]{0,80}", description or "", re.I)
    if not m:
        return ""
    snippet = m.group(0)
    return snippet if re.search(r"\d", snippet) else ""
