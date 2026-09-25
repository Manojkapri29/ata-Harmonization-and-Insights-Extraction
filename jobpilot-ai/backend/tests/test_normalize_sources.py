"""Job normalization, deduplication and source adapters (offline payloads)."""
from datetime import date, timedelta

import pytest

from app.services.normalize import (RawJob, annualize, canonical_url, cities_in, clean_html, dedupe_hash, normalize,
                                    parse_date, parse_experience, parse_salary)
from app.services.sources import REGISTRY, SearchQuery
from app.services.sources.api_sources import (parse_adzuna, parse_arbeitnow, parse_ashby, parse_greenhouse, parse_lever,
                                              parse_remoteok, parse_remotive, parse_themuse)
from app.services.sources.web_sources import extract_jobpostings, import_from_page, parse_feed, source_for_url


@pytest.mark.parametrize("text,expected", [
    ("₹4-6 LPA", (400000, 600000, "INR", "year")),
    ("Rs 35,000 - 45,000 per month", (35000, 45000, "INR", "month")),
    ("3 - 4.5 Lacs P.A.", (300000, 450000, "INR", "year")),
    ("$60k-$80k a year", (60000, 80000, "USD", "year")),
    ("Not disclosed", (None, None, "", "")),
])
def test_parse_salary(text, expected):
    assert parse_salary(text) == expected


def test_annualize_monthly_and_unlabelled_indian_monthly():
    assert annualize(42000, "month") == 504000
    assert annualize(30000, "") == 360000        # unlabelled small figure = monthly CTC
    assert annualize(600000, "") == 600000


@pytest.mark.parametrize("text,expected", [
    ("3-5 years", (3, 5)), ("3+ yrs", (3, None)), ("Minimum 2 years of experience", (2, None)),
    ("2 to 4 Yrs", (2, 4)), ("Fresher", (0, 1)), ("", (None, None)),
])
def test_parse_experience(text, expected):
    assert parse_experience(text) == expected


def test_parse_date_relative_and_iso():
    assert parse_date("3 days ago") == date.today() - timedelta(days=3)
    assert parse_date("2026-09-01T10:00:00Z") == date(2026, 9, 1)
    assert parse_date(1758800000000).year == 2025


def test_locations_and_ncr():
    assert cities_in("Gurgaon, Haryana") == {"Gurugram"}
    assert "Delhi NCR" in cities_in("Delhi/NCR")


def test_clean_html_and_canonical_url():
    assert clean_html("&lt;p&gt;SQL &amp;amp; Excel&lt;/p&gt;") == "SQL & Excel"
    assert canonical_url("https://www.x.com/job/1/?utm_source=a&id=2") == "https://x.com/job/1?id=2"


def test_normalize_extracts_fields():
    job = normalize(RawJob(source="t", title="Sr. MIS Executive", company="ABC Pvt Ltd", location="Gurgaon",
                           salary_text="₹5-7 LPA", experience_text="3-5 years",
                           description="Full-time role. Advanced Excel, VLOOKUP, Power Query and SQL. MBA preferred. "
                                       "Immediate joiners preferred."))
    assert job["location"] == "Gurugram"
    assert (job["salary_min"], job["salary_max"], job["salary_currency"]) == (500000, 700000, "INR")
    assert (job["experience_min"], job["experience_max"]) == (3, 5)
    assert {"Advanced Excel", "Power Query", "SQL", "VLOOKUP/XLOOKUP"} <= set(job["skills"])
    assert job["role_category"] == "MIS Executive"
    assert job["employment_type"] == "Full-time"
    assert "MBA" in job["education"]
    assert "Immediate" in job["notice_period"]


def test_dedupe_hash_same_job_across_boards():
    a = dedupe_hash("Sr. Data Analyst", "ABC Pvt Ltd", "Gurgaon, Haryana")
    b = dedupe_hash("Senior Data Analyst", "ABC", "Gurugram, India")
    c = dedupe_hash("Senior Data Analyst", "ABC", "Pune")
    assert a == b and a != c


def test_api_parsers():
    r = parse_remotive({"jobs": [{"id": 1, "title": "Data Analyst", "company_name": "A", "url": "u",
                                  "candidate_required_location": "India", "description": "<p>SQL</p>", "tags": ["sql"]}]})
    assert r[0].remote and r[0].source_job_id == "1"
    assert parse_arbeitnow({"data": [{"slug": "s", "title": "T", "company_name": "C", "remote": True}]})[0].remote
    ro = parse_remoteok([{"legal": "x"}, {"id": 5, "position": "BI Analyst", "company": "C", "salary_min": 50000,
                                          "salary_max": 70000}])
    assert len(ro) == 1 and ro[0].salary_currency == "USD"
    assert parse_themuse({"results": [{"name": "Analyst", "locations": [{"name": "Flexible / Remote"}],
                                       "company": {"name": "M"}, "refs": {"landing_page": "u"}}]})[0].remote
    gh = parse_greenhouse({"jobs": [{"id": 9, "title": "T", "location": {"name": "Noida"}, "absolute_url": "u",
                                     "content": "&lt;p&gt;x&lt;/p&gt;"}]}, "acme")
    assert gh[0].source_job_id == "acme:9"
    lv = parse_lever([{"id": "x", "text": "MIS Analyst", "categories": {"location": "Noida", "commitment": "Full-time"},
                       "hostedUrl": "u", "descriptionPlain": "About", "lists": [{"text": "Req", "content": "<li>SQL</li>"}],
                       "salaryRange": {"min": 500000, "max": 700000, "currency": "INR", "interval": "per-year-salary"}}], "co")
    assert "SQL" in lv[0].description and lv[0].salary_period == "year"
    assert parse_ashby({"jobs": [{"title": "DA", "isRemote": True, "jobUrl": "u"}]}, "co")[0].remote
    az = parse_adzuna({"results": [{"id": 1, "title": "Data Analyst", "company": {"display_name": "Z"},
                                    "location": {"display_name": "Noida"}, "salary_min": 400000, "salary_max": 600000}]})
    assert az[0].salary_period == "year"


JSONLD_PAGE = """<html><head><title>MIS Executive | Naukri</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"MIS Executive",
"description":"<p>Advanced Excel and VBA</p>","datePosted":"2026-09-20",
"hiringOrganization":{"@type":"Organization","name":"XYZ Retail","sameAs":"https://xyz.example"},
"jobLocation":{"@type":"Place","address":{"addressLocality":"Noida","addressRegion":"UP","addressCountry":"IN"}},
"baseSalary":{"@type":"MonetaryAmount","currency":"INR","value":{"@type":"QuantitativeValue","minValue":35000,"maxValue":45000,"unitText":"MONTH"}},
"experienceRequirements":{"@type":"OccupationalExperienceRequirements","monthsOfExperience":36},
"employmentType":"FULL_TIME","identifier":{"@type":"PropertyValue","value":"JOB-77"}}</script></head></html>"""


def test_jsonld_jobposting_extraction():
    jobs = extract_jobpostings(JSONLD_PAGE, "naukri", "https://www.naukri.com/job/77")
    assert len(jobs) == 1
    n = normalize(jobs[0])
    assert (n["title"], n["company"], n["source_job_id"]) == ("MIS Executive", "XYZ Retail", "JOB-77")
    assert n["salary_min"] == 420000 and n["salary_currency"] == "INR"
    assert n["experience_min"] == 3 and "Noida" in n["location"]


def test_import_from_page_falls_back_to_text():
    jobs = import_from_page("https://www.linkedin.com/jobs/view/1", "Data Analyst | Acme | LinkedIn",
                            "We need SQL and Power BI.")
    assert jobs[0].source == "linkedin" and jobs[0].title == "Data Analyst"


def test_rss_feed():
    xml = """<rss><channel><item><title>Data Analyst at Acme</title><link>https://x/1</link>
    <description>SQL</description><pubDate>Mon, 21 Sep 2026 10:00:00 +0000</pubDate><guid>g1</guid></item></channel></rss>"""
    j = parse_feed(xml)[0]
    assert (j.title, j.company, j.source_job_id) == ("Data Analyst", "Acme", "g1")


def test_assisted_sources_build_links_and_never_search():
    q = SearchQuery(keywords=["Data Analyst"], locations=["Noida"], posted_within_days=7, experience_min=3)
    for key in ("linkedin", "naukri", "indeed", "glassdoor", "foundit", "internshala"):
        a = REGISTRY[key]
        assert not a.supports_search
        links = a.search_links(q)
        assert links and all(l["url"].startswith("https://") for l in links)
    assert "noida" in REGISTRY["naukri"].search_links(q)[0]["url"]


def test_source_for_url():
    assert source_for_url("https://in.indeed.com/viewjob?jk=1") == "indeed"
    assert source_for_url("https://careers.example.com/x") == "url_import"
