"""Offline tests: no network needed. Payloads mirror each API's documented JSON shape."""
import io

import pandas as pd
import pytest
from docx import Document

from jobcopilot import sources, tracker
from jobcopilot.matcher import find_terms, keyword_gap, score_jobs
from jobcopilot.profile import EXAMPLE_PATH, load_profile
from jobcopilot.resume import cover_letter, tailor, to_docx, to_markdown, to_pdf

JD = ("We need a Data Analyst skilled in SQL, Advanced Excel (pivot tables, VLOOKUP), Power BI "
      "dashboards and Python. Experience with forecasting and stakeholder reporting is a plus.")


@pytest.fixture
def profile():
    return load_profile(EXAMPLE_PATH)


# ---------------------------------------------------------------- parsers

def test_parse_remotive():
    jobs = sources.parse_remotive({"jobs": [{
        "title": "Data Analyst", "company_name": "Acme", "url": "https://r/1",
        "candidate_required_location": "India", "publication_date": "2026-09-20T10:00:00",
        "description": "<p>SQL &amp; Python</p>", "tags": ["sql"], "salary": "",
    }]})
    j = jobs[0]
    assert (j.title, j.company, j.location, j.posted, j.remote) == ("Data Analyst", "Acme", "India", "2026-09-20", True)
    assert j.description == "SQL & Python"


def test_parse_arbeitnow_unix_date():
    jobs = sources.parse_arbeitnow({"data": [{
        "title": "BI Analyst", "company_name": "Beta", "location": "Berlin", "remote": False,
        "url": "https://a/1", "description": "<b>Power BI</b>", "created_at": 1758800000, "tags": [],
    }]})
    assert jobs[0].posted.startswith("2025-") and jobs[0].description == "Power BI"


def test_parse_remoteok_skips_legal_notice():
    jobs = sources.parse_remoteok([
        {"legal": "API terms"},
        {"position": "Data Scientist", "company": "Gamma", "url": "https://ro/1", "date": "2026-09-01T00:00:00+00:00",
         "description": "ML", "salary_min": 50000, "salary_max": 70000, "tags": ["python"]},
    ])
    assert len(jobs) == 1 and jobs[0].salary == "USD 50,000 - 70,000"


def test_parse_themuse():
    jobs = sources.parse_themuse({"results": [{
        "name": "Analyst", "company": {"name": "Muse Co"}, "locations": [{"name": "Flexible / Remote"}],
        "refs": {"landing_page": "https://m/1"}, "contents": "<p>Excel</p>", "publication_date": "2026-09-02T00:00:00Z",
        "categories": [{"name": "Data and Analytics"}],
    }]})
    assert jobs[0].remote is True and jobs[0].url == "https://m/1"


def test_parse_greenhouse_double_escaped_html():
    jobs = sources.parse_greenhouse({"jobs": [{
        "title": "Analyst", "location": {"name": "Bengaluru"}, "absolute_url": "https://gh/1",
        "updated_at": "2026-09-03T00:00:00-04:00", "content": "&lt;p&gt;SQL &amp;amp; Excel&lt;/p&gt;",
    }]}, "acme")
    assert jobs[0].description == "SQL & Excel" and jobs[0].company == "acme"


def test_parse_lever_ms_timestamp_and_lists():
    jobs = sources.parse_lever([{
        "text": "Business Analyst", "categories": {"location": "Mumbai", "team": "Ops", "commitment": "Full-time"},
        "hostedUrl": "https://lv/1", "createdAt": 1758800000000, "descriptionPlain": "About us",
        "lists": [{"text": "Requirements", "content": "<li>SQL</li><li>Tableau</li>"}],
    }], "acme")
    j = jobs[0]
    assert j.posted.startswith("2025-") and "Tableau" in j.description and j.tags == ["Ops", "Full-time"]


def test_parse_ashby_and_adzuna():
    a = sources.parse_ashby({"jobs": [{"title": "DA", "location": "Remote", "isRemote": True,
                                       "jobUrl": "https://ash/1", "descriptionPlain": "SQL"}]}, "co")
    z = sources.parse_adzuna({"results": [{"title": "<strong>Data</strong> Analyst", "company": {"display_name": "Z"},
                                           "location": {"display_name": "Delhi"}, "redirect_url": "https://az/1",
                                           "description": "Excel", "created": "2026-09-04T00:00:00Z",
                                           "salary_min": 400000, "salary_max": 600000}]})
    assert a[0].remote is True
    assert z[0].title == "Data Analyst" and z[0].salary == "400,000 - 600,000"


def test_parse_jobspy_dataframe():
    df = pd.DataFrame([{"site": "naukri", "title": "MIS Executive", "company": "X", "location": "Noida",
                        "job_url": "https://n/1", "job_url_direct": None, "description": "Excel MIS",
                        "date_posted": "2026-09-05", "is_remote": False, "min_amount": None,
                        "max_amount": None, "currency": None, "skills": "Excel, MIS"}])
    j = sources.parse_jobspy(df)[0]
    assert j.url == "https://n/1" and j.source == "JobSpy/naukri" and j.tags == ["Excel", "MIS"]


# ---------------------------------------------------------------- search orchestration

def test_search_filters_dedupes_and_isolates_failures(monkeypatch):
    def good(query, **_):
        mk = lambda t, c, loc: sources.Job(t, c, loc, "u", "desc", "fake")
        return [mk("Data Analyst", "A", "Pune, India"), mk("Data Analyst", "A", "Pune, India"),
                mk("Chef", "B", "India"), mk("Data Analyst", "C", "Berlin"), mk("Data Analyst", "D", "Remote")]

    def bad(query, **_):
        raise ConnectionError("down")

    monkeypatch.setitem(sources.SOURCES, "good", good)
    monkeypatch.setitem(sources.SOURCES, "bad", bad)
    jobs, errors = sources.search("data analyst", "India", ["good", "bad"], include_remote=True)
    assert [j.company for j in jobs] == ["A", "D"]
    assert "bad" in errors
    jobs, _ = sources.search("data analyst", "India", ["good"], include_remote=False)
    assert [j.company for j in jobs] == ["A"]


# ---------------------------------------------------------------- matching

def test_find_terms_aliases_and_boundaries():
    terms = find_terms("Strong MS Excel, PowerBI and ML. Knowledge of HTML is nice.")
    assert {"Excel", "Power BI", "Machine Learning"} <= terms
    assert "SQL" not in find_terms("We use NoSQLite")  # no partial-word matches


def test_scores_rank_relevant_job_higher(profile):
    good = sources.Job("Data Analyst", "A", "India", "u", JD, "t")
    bad = sources.Job("Senior Chef", "B", "India", "u", "Cook Italian food in a busy kitchen.", "t")
    m_good, m_bad = score_jobs([good, bad], profile)
    assert m_good.score > m_bad.score
    assert "SQL" in m_good.matched and "Power BI" in m_good.missing


def test_keyword_gap(profile):
    matched, missing = keyword_gap(JD, profile)
    assert "Python" in matched and "Power BI" in missing


# ---------------------------------------------------------------- resume

def test_tailor_reorders_but_never_invents(profile):
    t = tailor(profile, "Excel MIS reporting dashboards pivot tables", max_bullets=2, max_projects=2)
    all_bullets = {b for e in profile["experience"] for b in e["bullets"]} | \
                  {b for p in profile["projects"] for b in p["bullets"]}
    for e in t["experience"]:
        assert len(e["bullets"]) <= 2 and set(e["bullets"]) <= all_bullets
    assert len(t["projects"]) == 2
    mis = next(e for e in t["experience"] if e["title"] == "MIS Executive")
    assert "Excel" in mis["bullets"][0]
    assert profile["experience"][2]["bullets"] != [] and len(profile["projects"]) == 5  # original untouched


def test_exports(profile):
    t = tailor(profile, JD)
    md = to_markdown(t)
    assert md.startswith("# Manoj Kapri") and "## Education" in md
    doc = Document(io.BytesIO(to_docx(t)))
    assert "Manoj Kapri" in doc.paragraphs[0].text
    pdf = to_pdf({**t, "summary": "Rs ₹ sales – “quoted”"})
    assert pdf[:4] == b"%PDF"


def test_cover_letter(profile):
    letter = cover_letter(profile, "Data Analyst", "Acme", JD)
    assert "Data Analyst role at Acme" in letter and letter.rstrip().splitlines()[-2] == "Manoj Kapri"
    assert ".." not in letter


# ---------------------------------------------------------------- tracker

def test_tracker_roundtrip(tmp_path):
    path = tmp_path / "apps.csv"
    df = tracker.load(path)
    job = sources.Job("DA", "Acme", "Pune", "https://x", "", "t").to_dict()
    df, added = tracker.add(df, job, 77)
    df, added_again = tracker.add(df, job, 77)
    assert added and not added_again
    tracker.save(df, path)
    back = tracker.load(path)
    assert len(back) == 1 and back.at[0, "status"] == "Saved" and back.at[0, "score"] == "77"
    assert tracker.summary(back)["Saved"] == 1
