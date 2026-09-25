"""Explainable job <-> profile matching. No paid AI: keyword coverage + TF-IDF.

score (0-100) = 50 * keyword coverage   (share of the job's known skills you have)
              + 30 * text similarity     (TF-IDF cosine, scaled; 0.30 counts as full)
              + 20 * title fit           (does the job title look like a target role)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .profile import profile_skills, profile_text

# canonical term -> aliases (lower-case). Extend freely.
SKILL_VOCAB: dict[str, list[str]] = {
    # programming / data
    "Python": ["python"], "SQL": ["sql", "mysql", "postgresql", "postgres", "t-sql"],
    "R": [r"\br\b programming", "r language", "rstudio"],
    "Pandas": ["pandas"], "NumPy": ["numpy"], "Scikit-learn": ["scikit-learn", "sklearn"],
    "TensorFlow": ["tensorflow"], "PyTorch": ["pytorch"], "Keras": ["keras"],
    "Matplotlib": ["matplotlib"], "Seaborn": ["seaborn"], "Plotly": ["plotly"],
    "Jupyter": ["jupyter"], "Git": ["git", "github"], "Docker": ["docker"],
    "Flask": ["flask"], "Streamlit": ["streamlit"], "FastAPI": ["fastapi"],
    "MLflow": ["mlflow"], "DVC": ["dvc"], "Airflow": ["airflow"], "Spark": ["spark", "pyspark"],
    "AWS": ["aws", "amazon web services"], "Azure": ["azure"], "GCP": ["gcp", "google cloud"],
    "BigQuery": ["bigquery"], "Snowflake": ["snowflake"], "Databricks": ["databricks"],
    # BI / office
    "Excel": ["excel", "ms excel", "microsoft excel", "spreadsheets"],
    "Advanced Excel": ["advanced excel", "vlookup", "xlookup", "pivot table", "pivot tables", "power query"],
    "VBA": ["vba", "macros"], "Power BI": ["power bi", "powerbi", "dax"],
    "Tableau": ["tableau"], "Looker": ["looker"], "Google Sheets": ["google sheets"],
    "PowerPoint": ["powerpoint", "ms office", "microsoft office"],
    # methods
    "Machine Learning": ["machine learning", r"\bml\b"], "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"], "Statistics": ["statistics", "statistical"],
    "Hypothesis Testing": ["hypothesis testing", "a/b testing", "ab testing"],
    "Regression": ["regression"], "Classification": ["classification"],
    "Time Series": ["time series", "time-series"], "Forecasting": ["forecasting", "forecast"],
    "EDA": ["eda", "exploratory data analysis"], "Data Cleaning": ["data cleaning", "data cleansing", "data wrangling", "data preparation"],
    "Data Visualization": ["data visualization", "data visualisation", "dashboards", "dashboard"],
    "Feature Engineering": ["feature engineering"], "ETL": ["etl", "elt", "data pipeline", "data pipelines"],
    "Data Modeling": ["data modeling", "data modelling"], "Data Warehousing": ["data warehouse", "data warehousing"],
    "MLOps": ["mlops"], "Model Deployment": ["model deployment", "deploy models", "deployment"],
    "Reporting": ["reporting", "reports", "mis"], "KPI Tracking": ["kpi", "kpis", "metrics"],
    # business
    "Business Analysis": ["business analysis", "business analyst"], "Requirement Gathering": ["requirement gathering", "requirements gathering"],
    "Stakeholder Management": ["stakeholder", "stakeholders"], "Project Management": ["project management"],
    "Market Research": ["market research"], "Financial Analysis": ["financial analysis", "financial modeling", "financial modelling"],
    "Sales Analysis": ["sales analysis", "sales data"], "Customer Analytics": ["customer analytics", "customer behavior", "customer behaviour", "segmentation"],
    "Supply Chain": ["supply chain"], "CRM": ["crm", "salesforce"], "ERP": ["erp", "sap"],
    "Communication": ["communication skills", "written communication", "verbal communication"],
    "Problem Solving": ["problem solving", "problem-solving"], "Attention to Detail": ["attention to detail"],
    "Customer Service": ["customer service", "customer support"], "Email Support": ["email support", "chat support"],
}

_PATTERNS = {
    canon: re.compile("|".join(a if a.startswith(r"\b") else rf"(?<![\w+#]){re.escape(a)}(?![\w+#])" for a in aliases), re.I)
    for canon, aliases in SKILL_VOCAB.items()
}


def find_terms(text: str) -> set[str]:
    """Canonical vocabulary terms present in text."""
    return {canon for canon, pat in _PATTERNS.items() if pat.search(text or "")}


@dataclass
class Match:
    score: int
    coverage: float
    similarity: float
    title_fit: float
    matched: list[str]
    missing: list[str]


def _title_fit(title: str, targets: list[str]) -> float:
    t = title.lower()
    best = 0.0
    for role in targets:
        words = [w for w in re.findall(r"[a-z]+", role.lower()) if len(w) > 2]
        if not words:
            continue
        hit = sum(w in t for w in words) / len(words)
        best = max(best, hit)
    return best


def score_jobs(jobs: list, profile: dict) -> list[Match]:
    """Score many jobs at once (one TF-IDF fit for the batch)."""
    if not jobs:
        return []
    ptext = profile_text(profile)
    pterms = find_terms(ptext) | find_terms(" ".join(profile_skills(profile)))
    docs = [f"{j.title}\n{j.description}" for j in jobs]

    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    matrix = vec.fit_transform([ptext] + docs)
    sims = cosine_similarity(matrix[0], matrix[1:]).ravel()

    targets = profile.get("target_roles") or [profile.get("headline", "")]
    results = []
    for job, doc, sim in zip(jobs, docs, sims):
        jterms = find_terms(doc)
        matched = sorted(jterms & pterms)
        missing = sorted(jterms - pterms)
        coverage = len(matched) / len(jterms) if jterms else 0.0
        tfit = _title_fit(job.title, targets)
        score = 50 * coverage + 30 * min(1.0, sim / 0.30) + 20 * tfit
        results.append(Match(round(score), round(coverage, 2), round(float(sim), 3), round(tfit, 2), matched, missing))
    return results


def keyword_gap(job_text: str, profile: dict) -> tuple[list[str], list[str]]:
    """(matched, missing) vocabulary terms for one job description."""
    jterms = find_terms(job_text)
    pterms = find_terms(profile_text(profile))
    return sorted(jterms & pterms), sorted(jterms - pterms)


def relevance(text: str, job_terms: set[str]) -> int:
    """How many of the job's terms a piece of resume text mentions."""
    return len(find_terms(text) & job_terms)
