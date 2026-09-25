"""API + database flows, including the critical UX flow:
Find Jobs -> open job -> Generate Application Kit -> Mark Applied -> follow-ups scheduled."""
from datetime import date, timedelta

from sqlalchemy import inspect, select

from app.models import Application, Followup, Job, JobSkill

from .conftest import FIXTURES


def test_tables_and_indexes_exist(db):
    insp = inspect(db.get_bind())
    tables = set(insp.get_table_names())
    for t in ["users", "profiles", "resumes", "resume_versions", "jobs", "job_skills", "job_sources", "applications",
              "contacts", "communications", "followups", "search_profiles", "ai_analysis", "settings",
              "background_tasks", "notifications"]:
        assert t in tables
    idx = {i["name"] for i in insp.get_indexes("jobs")}
    assert "ix_jobs_match_score" in idx and "ix_jobs_dedupe_hash" in idx


def test_models_cascade(db):
    job = Job(source="t", source_job_id="cascade-1", title="X", dedupe_hash="h")
    job.job_skills.append(JobSkill(skill="SQL"))
    db.add(job)
    db.flush()
    app = Application(job_id=job.id, status="Applied")
    db.add(app)
    db.flush()
    db.add(Followup(application_id=app.id, job_id=job.id, day_offset=3, due_date=date.today(), channel="email"))
    db.flush()
    db.delete(job)
    db.flush()
    assert db.scalar(select(Followup).where(Followup.application_id == app.id)) is None


def test_health_and_seed(client):
    assert client.get("/api/health").json()["status"] == "ok"
    p = client.get("/api/profile").json()
    assert p["full_name"] == "Manoj Kapri" and p["notice_period"] == "Immediate Joiner"
    assert p["current_salary_monthly"] == 42000
    sources = {s["key"]: s for s in client.get("/api/sources").json()}
    assert sources["linkedin"]["kind"] == "assisted" and not sources["linkedin"]["supports_search"]
    assert sources["adzuna"]["requires_credentials"] == ["ADZUNA_APP_ID", "ADZUNA_APP_KEY"]
    assert sources["demo"]["enabled"] is False


def test_critical_flow(client):
    # 1. Find jobs (background task; demo source works offline)
    r = client.post("/api/jobs/search", json={"keywords": ["Data Analyst", "MIS Executive", "Reporting Analyst", "BI Analyst"],
                                              "locations": ["Delhi NCR", "Noida", "Gurugram"], "sources": ["demo", "linkedin"],
                                              "posted_within_days": 30})
    assert r.status_code == 202
    task = client.get(f"/api/tasks/{r.json()['id']}").json()
    assert task["status"] == "completed", task["error"]
    res = task["result"]
    assert res["sources"]["demo"]["new"] == 4          # the Bengaluru data-engineer job is filtered out
    assert res["sources"]["linkedin"]["status"] == "assisted" and res["assisted_links"]
    assert res["high_matches"] >= 1
    notes = client.get("/api/notifications").json()
    assert notes and notes[0]["title"] == "🔥 NEW HIGH MATCH JOB" and "application_url" in notes[0]["body"]

    # 2. Run again: dedupe, nothing new
    r2 = client.post("/api/jobs/search", json={"keywords": ["Data Analyst", "MIS Executive"], "sources": ["demo"],
                                               "locations": [], "posted_within_days": 30}).json()
    assert client.get(f"/api/tasks/{r2['id']}").json()["result"]["new_jobs"] == 0

    # 3. Upload master resume
    with open(FIXTURES / "sample_resume.txt", "rb") as f:
        up = client.post("/api/resumes", files={"file": ("resume.txt", f, "text/plain")})
    assert up.status_code == 201 and up.json()["is_master"]

    # 4. List + filter + open a job
    jobs = client.get("/api/jobs", params={"sort": "match_score", "min_score": 60}).json()
    assert jobs["total"] >= 3
    top = jobs["items"][0]
    assert top["match_score"] >= jobs["items"][-1]["match_score"]
    assert client.get("/api/jobs", params={"location": "Noida"}).json()["total"] >= 1
    assert client.get("/api/jobs", params={"role": "MIS Executive"}).json()["items"][0]["role_category"] == "MIS Executive"
    detail = client.get(f"/api/jobs/{top['id']}").json()
    assert detail["match_details"]["matching_skills"]
    jd = client.post(f"/api/jobs/{top['id']}/analyze").json()
    assert jd["required_skills"]

    # 5. Generate Application Kit
    k = client.post(f"/api/jobs/{top['id']}/kit")
    assert k.status_code == 202
    kt = client.get(f"/api/tasks/{k.json()['id']}").json()
    assert kt["status"] == "completed", kt["error"]
    kit = client.get(f"/api/jobs/{top['id']}/kit").json()
    assert set(kit["communications"]) == {"cover_letter", "email", "whatsapp", "linkedin_note", "linkedin_dm"}
    assert kit["resume_version"]["filename_base"].endswith("_v1")
    assert kit["resume_ats"]["label"] == "ATS compatibility estimate"
    rv_id = kit["resume_version"]["id"]
    assert client.get(f"/api/resumes/versions/{rv_id}/download?format=docx").status_code == 200
    pdf = client.get(f"/api/resumes/versions/{rv_id}/download?format=pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    # a second tailoring makes v2
    v2 = client.post(f"/api/jobs/{top['id']}/resume?use_ai=false").json()
    assert v2["version"] == 2 and v2["filename_base"].endswith("_v2")

    # 6. Mark applied -> follow-ups scheduled
    a = client.post(f"/api/jobs/{top['id']}/apply", json={}).json()
    assert a["status"] == "Applied"
    days = [f["day"] for f in a["followups"]]
    assert days == [3, 7, 14]
    assert a["next_followup_date"] == (date.today() + timedelta(days=3)).isoformat()
    apps = client.get("/api/applications").json()
    assert apps[0]["status"] == "Applied" and apps[0]["resume_version_name"]

    # 7. Sending needs explicit human confirmation
    comm_id = kit["communication_ids"]["email"]
    assert client.patch(f"/api/communications/{comm_id}", json={"mark_sent": True}).status_code == 409
    sent = client.patch(f"/api/communications/{comm_id}", json={"mark_sent": True, "confirm": True}).json()
    assert sent["status"] == "sent"
    assert client.get(f"/api/applications/{a['application_id']}").json()["application"]["status"] == "HR Contacted"
    links = client.get(f"/api/communications/{comm_id}/links").json()
    assert links["mailto"].startswith("mailto:")

    # 8. Follow-up done, status change stops reminders
    fu = client.get("/api/followups").json()[0]
    assert client.post(f"/api/followups/{fu['id']}/draft").json()["body"]
    assert client.patch(f"/api/followups/{fu['id']}", json={"status": "done"}).json()["status"] == "done"
    client.patch(f"/api/applications/{a['application_id']}", json={"status": "Interview"})
    assert not [f for f in client.get("/api/followups").json() if f["application_id"] == a["application_id"]]

    # 9. Dashboard / analytics
    d = client.get("/api/dashboard").json()
    assert d["applications"] == 1 and d["interviews"] == 1 and d["response_rate"] == 100.0
    an = client.get("/api/analytics").json()
    assert an["rates"]["interview_conversion_rate"] == 100.0
    assert an["funnel"][0]["stage"] == "Discovered"


def test_linkedin_note_length_enforced_on_edit(client):
    job = client.post("/api/jobs", json={"title": "BI Analyst", "company": "Beta", "description": "Power BI and SQL"}).json()
    note = client.post(f"/api/jobs/{job['id']}/communications", json={"channels": ["linkedin_note"]}).json()[0]
    r = client.patch(f"/api/communications/{note['id']}", json={"body": "x" * 301})
    assert r.status_code == 422


def test_manual_and_page_import(client):
    j = client.post("/api/jobs", json={"title": "Reporting Analyst", "company": "Gamma", "location": "Gurgaon",
                                       "description": "Advanced Excel, Power BI, SQL. 3-5 years.", "salary_text": "₹6-8 LPA"}).json()
    assert j["location"] == "Gurugram" and j["salary_max"] == 800000 and j["status"] == "Saved"
    page = client.post("/api/jobs/import/page", json={
        "url": "https://www.naukri.com/job-listings-77", "title": "MIS Executive",
        "jsonld": [{"@type": "JobPosting", "title": "MIS Executive", "description": "Advanced Excel",
                    "hiringOrganization": {"name": "XYZ"}, "jobLocation": {"address": {"addressLocality": "Noida"}}}]}).json()
    assert page[0]["source"] == "naukri" and page[0]["company"] == "XYZ"
    assert client.post("/api/jobs/import/page", json={"url": ""}).status_code == 422


def test_contacts_and_search_profiles(client):
    job = client.post("/api/jobs", json={"title": "Data Analyst", "company": "Delta"}).json()
    c = client.post("/api/contacts", json={"job_id": job["id"], "name": "Priya Sharma", "email": "hr@delta.example",
                                           "source_note": "Company careers page"}).json()
    assert c["company"] == "Delta"
    assert client.post("/api/contacts", json={"email": "not-an-email"}).status_code == 422
    msg = client.post(f"/api/jobs/{job['id']}/communications", json={"channels": ["email"]}).json()[0]
    assert msg["body"].startswith("Hi Priya,")
    sp = client.post("/api/search-profiles", json={"name": "Remote BI", "keywords": ["BI Analyst"], "locations": ["Remote"],
                                                   "sources": ["demo"], "posted_within_days": 30}).json()
    t = client.post(f"/api/search-profiles/{sp['id']}/run").json()
    assert client.get(f"/api/tasks/{t['id']}").json()["status"] == "completed"


def test_settings_never_store_keys(client):
    s = client.put("/api/settings", json={"ai": {"provider": "ollama", "model": "llama3.1", "api_key": "secret"},
                                          "high_match_threshold": 80}).json()
    assert "api_key" not in s["ai"] and s["high_match_threshold"] == 80
    assert client.post("/api/settings/ai/test").json()["provider"] == "ollama"
    client.put("/api/settings", json={"ai": {}, "high_match_threshold": 75})


def test_import_export_roundtrip(client):
    csv_data = "title,company,location,description,salary_text\nMIS Analyst,Epsilon,Noida,Advanced Excel and VBA,₹5 LPA\n,NoTitle,,,\n"
    r = client.post("/api/import/jobs", files={"file": ("jobs.csv", csv_data.encode(), "text/csv")}).json()
    assert r == {"imported": 1, "updated": 0, "skipped": 1}
    for entity in ("jobs", "applications", "contacts", "analytics"):
        for fmt in ("csv", "xlsx", "json"):
            assert client.get(f"/api/export/{entity}", params={"format": fmt}).status_code == 200
    xlsx = client.get("/api/export/jobs", params={"format": "xlsx"}).content
    r2 = client.post("/api/import/jobs", files={"file": ("jobs.xlsx", xlsx, "application/octet-stream")}).json()
    assert r2["imported"] == 0 and r2["updated"] >= 1


def test_resume_analyze_with_pasted_jd(client):
    r = client.post("/api/resumes/analyze", json={"jd_text": "Need SQL, Tableau and Power BI dashboards", "job_title": "BI Analyst"}).json()
    assert "Tableau" in r["missing_skills"] and "SQL" in r["skills_present"]
    general = client.post("/api/resumes/tailor", json={"use_ai": False}).json()
    assert general["kind"] == "ats_general"


def test_errors(client):
    assert client.get("/api/jobs/999999").status_code == 404
    assert client.post("/api/resumes", files={"file": ("x.odt", b"abc", "application/octet-stream")}).status_code == 415
    assert client.patch("/api/applications/999999", json={"status": "Applied"}).status_code == 404
