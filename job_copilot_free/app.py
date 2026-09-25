"""Free Job Copilot - Streamlit UI.

Run:  streamlit run app.py
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from jobcopilot import sources, tracker
from jobcopilot.matcher import keyword_gap, score_jobs
from jobcopilot.profile import EXAMPLE_PATH, PROFILE_PATH, load_profile, parse_profile, save_profile
from jobcopilot.resume import cover_letter, tailor, to_docx, to_markdown, to_pdf

st.set_page_config(page_title="Free Job Copilot", page_icon="🧭", layout="wide")

SOURCE_LABELS = {
    "remotive": "Remotive (remote jobs)",
    "arbeitnow": "Arbeitnow (Europe + remote)",
    "remoteok": "RemoteOK (remote jobs)",
    "themuse": "The Muse (Data & Analytics)",
    "greenhouse": "Greenhouse company boards",
    "lever": "Lever company boards",
    "ashby": "Ashby company boards",
    "adzuna": "Adzuna (India + 15 countries, free key)",
    "jobspy": "LinkedIn / Indeed / Naukri via JobSpy (unofficial)",
}


def secret(name: str) -> str:
    try:
        return st.secrets.get(name, "")
    except Exception:  # no secrets.toml
        return ""


# ---------------------------------------------------------------- state

if "profile_text" not in st.session_state:
    path = PROFILE_PATH if PROFILE_PATH.exists() else EXAMPLE_PATH
    st.session_state.profile_text = path.read_text(encoding="utf-8")
if "jobs" not in st.session_state:
    st.session_state.jobs = pd.DataFrame()
if "tracker" not in st.session_state:
    st.session_state.tracker = tracker.load()

try:
    profile = parse_profile(st.session_state.profile_text)
except Exception as e:
    st.error(f"Your profile YAML has an error - fix it in the Profile tab.\n\n{e}")
    profile = load_profile(EXAMPLE_PATH)

placeholders = sorted(set(re.findall(r"<[^<>\n]{2,60}>", st.session_state.profile_text)))

st.title("🧭 Free Job Copilot")
st.caption("Find jobs from free sources, see how well you match, and build a tailored resume "
           "+ cover letter for each one. You review and apply yourself - quality over spam.")
if placeholders:
    st.warning(f"Your profile still has {len(placeholders)} placeholder(s) like `{placeholders[0]}`. "
               "Fill them in the **Profile** tab before downloading resumes.")

tab_find, tab_tailor, tab_track, tab_profile = st.tabs(
    ["🔎 Find jobs", "📝 Tailor resume", "📋 Tracker", "👤 Profile"])

# ---------------------------------------------------------------- Find jobs

with tab_find:
    c1, c2 = st.columns([2, 1])
    query = c1.text_input("Job titles / keywords (comma-separated)",
                          ", ".join(profile.get("target_roles", [])) or "data analyst")
    location = c2.text_input("Location (blank = anywhere)", "India")
    include_remote = c2.checkbox("Also include remote jobs", True)

    chosen = st.multiselect("Sources", list(SOURCE_LABELS), default=["remotive", "arbeitnow", "remoteok", "themuse"],
                            format_func=SOURCE_LABELS.get)
    options: dict[str, dict] = {}
    with st.expander("Source settings (company boards, API keys, JobSpy)"):
        st.markdown("Company board names come from careers URLs: `boards.greenhouse.io/<name>`, "
                    "`jobs.lever.co/<name>`, `jobs.ashbyhq.com/<name>`.")
        gh = st.text_input("Greenhouse companies", "")
        lv = st.text_input("Lever companies", "")
        ab = st.text_input("Ashby companies", "")
        options.update(greenhouse={"companies": gh}, lever={"companies": lv}, ashby={"companies": ab})

        st.markdown("**Adzuna** - free key at [developer.adzuna.com](https://developer.adzuna.com) "
                    "(or put `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` in `.streamlit/secrets.toml`).")
        a1, a2, a3 = st.columns(3)
        options["adzuna"] = {
            "app_id": a1.text_input("Adzuna app_id", secret("ADZUNA_APP_ID")),
            "app_key": a2.text_input("Adzuna app_key", secret("ADZUNA_APP_KEY"), type="password"),
            "country": a3.text_input("Adzuna country code", "in"),
        }
        st.markdown("**JobSpy** (optional, `pip install python-jobspy`) scrapes public listings. "
                    "It is unofficial: expect rate limits, and use it for personal search only.")
        j1, j2, j3 = st.columns(3)
        options["jobspy"] = {
            "sites": j1.text_input("Sites", "indeed,linkedin,naukri"),
            "results": j2.number_input("Results per site", 10, 100, 30),
            "hours_old": j3.number_input("Posted within (hours)", 24, 720, 168),
        }

    if st.button("Search jobs", type="primary", disabled=not chosen):
        with st.spinner("Fetching from " + ", ".join(chosen) + " ..."):
            jobs, errors = sources.search(query, location, chosen, include_remote, options)
        for name, err in errors.items():
            st.warning(f"{SOURCE_LABELS[name]} failed: {err}")
        if jobs:
            matches = score_jobs(jobs, profile)
            rows = []
            for j, m in zip(jobs, matches):
                d = j.to_dict()
                d.update(score=m.score, matched=", ".join(m.matched), missing=", ".join(m.missing))
                rows.append(d)
            st.session_state.jobs = pd.DataFrame(rows).sort_values("score", ascending=False, ignore_index=True)
        else:
            st.session_state.jobs = pd.DataFrame()
            st.info("No jobs found. Try broader keywords, clear the location, or add sources.")

    df = st.session_state.jobs
    if not df.empty:
        min_score = st.slider("Minimum match score", 0, 100, 30)
        view = df[df.score >= min_score]
        st.write(f"**{len(view)}** of {len(df)} jobs (sorted by match score)")
        st.dataframe(
            view[["score", "title", "company", "location", "source", "posted", "salary", "matched", "missing", "url"]],
            column_config={
                "score": st.column_config.ProgressColumn("Match", min_value=0, max_value=100, format="%d"),
                "url": st.column_config.LinkColumn("Link", display_text="Open"),
            },
            hide_index=True, width="stretch",
        )
        pick = st.multiselect("Save to tracker", view.index,
                              format_func=lambda i: f"{df.at[i, 'score']} | {df.at[i, 'title']} - {df.at[i, 'company']}")
        if st.button("Save selected", disabled=not pick):
            added = 0
            for i in pick:
                st.session_state.tracker, ok = tracker.add(st.session_state.tracker, df.loc[i].to_dict(), df.at[i, "score"])
                added += ok
            tracker.save(st.session_state.tracker)
            st.success(f"Saved {added} job(s) to the tracker.")
        st.download_button("Download results (CSV)", view.to_csv(index=False), "jobs.csv", "text/csv")

# ---------------------------------------------------------------- Tailor resume

with tab_tailor:
    df = st.session_state.jobs
    choices = ["Paste a job description"] + ([f"{r.title} - {r.company}" for r in df.itertuples()] if not df.empty else [])
    choice = st.selectbox("Job", range(len(choices)), format_func=lambda i: choices[i])
    if choice == 0:
        t1, t2 = st.columns(2)
        job_title = t1.text_input("Job title", "Data Analyst")
        company = t2.text_input("Company", "")
        job_text = st.text_area("Job description", height=220, placeholder="Paste the full job description here")
    else:
        row = df.iloc[choice - 1]
        job_title, company, job_text = row.title, row.company, f"{row.title}\n{row.description}"
        with st.expander("Job description"):
            st.write(row.description)
            st.markdown(f"[Open posting]({row.url})")

    if job_text.strip():
        matched, missing = keyword_gap(job_text, profile)
        g1, g2 = st.columns(2)
        g1.success("**You have:** " + (", ".join(matched) or "-"))
        g2.error("**Job asks for, not in your profile:** " + (", ".join(missing) or "-"))
        st.caption("If you genuinely have a missing skill, add it (with proof in a bullet) in the Profile tab. "
                   "Don't add skills you can't defend in an interview.")

        s1, s2 = st.columns(2)
        max_bullets = s1.slider("Bullets per role/project", 2, 6, 4)
        max_projects = s2.slider("Projects to show", 1, 5, 3)
        tailored = tailor(profile, job_text, max_bullets, max_projects)
        slug = re.sub(r"\W+", "_", f"{profile.get('name', 'resume')}_{company or job_title}").strip("_")

        r1, r2 = st.columns([3, 2])
        with r1:
            st.subheader("Resume preview")
            st.markdown(to_markdown(tailored))
        with r2:
            st.subheader("Download")
            st.download_button("Resume (.docx - editable)", to_docx(tailored), f"{slug}.docx",
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            st.download_button("Resume (.pdf)", to_pdf(tailored), f"{slug}.pdf", "application/pdf")
            st.subheader("Cover letter")
            letter = st.text_area("Edit before sending", cover_letter(profile, job_title, company or "your company", job_text),
                                  height=380)
            st.download_button("Cover letter (.txt)", letter, f"{slug}_cover_letter.txt")

# ---------------------------------------------------------------- Tracker

with tab_track:
    tdf = st.session_state.tracker
    counts = tracker.summary(tdf)
    cols = st.columns(len(counts))
    for col, (status, n) in zip(cols, counts.items()):
        col.metric(status, n)
    edited = st.data_editor(
        tdf, hide_index=True, width="stretch", num_rows="dynamic",
        column_config={
            "status": st.column_config.SelectboxColumn("status", options=tracker.STATUSES),
            "url": st.column_config.LinkColumn("url"),
            "key": None,
        },
    )
    b1, b2, b3 = st.columns(3)
    if b1.button("Save tracker"):
        st.session_state.tracker = edited.fillna("")
        tracker.save(st.session_state.tracker)
        st.success("Saved to data/applications.csv")
    b2.download_button("Download tracker (CSV)", edited.to_csv(index=False), "applications.csv", "text/csv")
    up = b3.file_uploader("Restore tracker CSV", type="csv", label_visibility="collapsed")
    if up is not None and st.session_state.get("tracker_upload") != up.file_id:
        st.session_state.tracker_upload = up.file_id
        restored = pd.read_csv(up, dtype=str).fillna("")
        for col in tracker.COLUMNS:
            if col not in restored:
                restored[col] = ""
        st.session_state.tracker = restored[tracker.COLUMNS]
        tracker.save(st.session_state.tracker)
        st.rerun()
    st.caption("On free cloud hosting the disk resets on restart - download the CSV regularly.")

# ---------------------------------------------------------------- Profile

with tab_profile:
    st.markdown("Your **master profile** (YAML). Write everything true about you here; "
                "each resume is built by choosing from it. Add numbers wherever you can.")
    text = st.text_area("profile.yaml", st.session_state.profile_text, height=600)
    p1, p2, p3 = st.columns(3)
    if p1.button("Save profile", type="primary"):
        try:
            save_profile(text)
            st.session_state.profile_text = text
            st.success(f"Saved to {PROFILE_PATH.name}")
            st.rerun()
        except Exception as e:
            st.error(f"Not saved - YAML error: {e}")
    p2.download_button("Download profile.yaml", text, "profile.yaml")
    up = p3.file_uploader("Upload profile.yaml", type=["yaml", "yml"], label_visibility="collapsed")
    if up is not None and st.session_state.get("profile_upload") != up.file_id:
        st.session_state.profile_upload = up.file_id
        st.session_state.profile_text = up.getvalue().decode("utf-8")
        st.rerun()
