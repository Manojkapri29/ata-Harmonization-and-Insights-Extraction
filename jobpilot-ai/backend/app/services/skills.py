"""Skill vocabulary, role taxonomy and keyword extraction. Pure functions, no I/O."""
from __future__ import annotations

import re
from collections import Counter

# canonical skill -> aliases (lower case). Word-boundary matched.
SKILL_VOCAB: dict[str, list[str]] = {
    # Excel & reporting
    "Advanced Excel": ["advanced excel", "advance excel", "ms excel advanced", "excel (advanced)"],
    "Excel": ["excel", "ms excel", "microsoft excel", "spreadsheets", "spreadsheet"],
    "VLOOKUP/XLOOKUP": ["vlookup", "xlookup", "hlookup", "index match", "index-match"],
    "Pivot Tables": ["pivot table", "pivot tables", "pivot", "pivots"],
    "Power Query": ["power query", "powerquery", "m query"],
    "Power Pivot": ["power pivot", "powerpivot"],
    "VBA/Macros": ["vba", "macros", "macro", "excel macros"],
    "MIS Reporting": ["mis", "mis reporting", "mis reports", "management information system", "management information systems"],
    "Management Reporting": ["management reporting", "management reports", "management dashboards", "business reporting"],
    "Dashboard Development": ["dashboard", "dashboards", "dashboarding", "dashboard development"],
    "Reporting Automation": ["reporting automation", "report automation", "automate reports", "automated reports", "automation of reports", "automating reports"],
    "Data Validation": ["data validation", "data accuracy", "data quality", "data integrity", "reconciliation", "reconcile"],
    "Data Analysis": ["data analysis", "data analytics", "analyse data", "analyze data", "analytical skills"],
    "Data Cleaning": ["data cleaning", "data cleansing", "data wrangling", "data preparation"],
    "Data Visualization": ["data visualization", "data visualisation", "visualization", "visualisation"],
    "KPI Tracking": ["kpi", "kpis", "key performance indicators", "metrics tracking"],
    "Google Sheets": ["google sheets", "gsheet", "gsheets"],
    "PowerPoint": ["powerpoint", "ppt", "presentations"],
    "MS Office": ["ms office", "microsoft office", "ms-office"],
    # BI
    "Power BI": ["power bi", "powerbi", "power-bi", "pbi"],
    "DAX": ["dax"],
    "Tableau": ["tableau"],
    "Looker": ["looker", "looker studio", "google data studio", "data studio"],
    "Qlik": ["qlik", "qlikview", "qlik sense"],
    "SSRS": ["ssrs"], "SSIS": ["ssis"],
    # Data / programming
    "SQL": ["sql", "mysql", "postgresql", "postgres", "t-sql", "tsql", "pl/sql", "sql server", "ms sql", "oracle sql", "sqlite"],
    "Python": ["python"],
    "Pandas": ["pandas"], "NumPy": ["numpy"],
    "R": ["r programming", "r language", "rstudio"],
    "Statistics": ["statistics", "statistical analysis", "statistical"],
    "Machine Learning": ["machine learning"],
    "ETL": ["etl", "elt", "data pipeline", "data pipelines"],
    "Data Warehousing": ["data warehouse", "data warehousing", "data mart"],
    "Data Modeling": ["data modeling", "data modelling", "star schema"],
    "BigQuery": ["bigquery"], "Snowflake": ["snowflake"], "Azure": ["azure"], "AWS": ["aws"],
    "Forecasting": ["forecasting", "forecast"],
    "A/B Testing": ["a/b testing", "ab testing", "hypothesis testing"],
    # Business
    "Business Analysis": ["business analysis", "business analyst", "brd", "frd"],
    "Requirement Gathering": ["requirement gathering", "requirements gathering", "requirement analysis", "requirements analysis"],
    "Stakeholder Management": ["stakeholder management", "stakeholders", "stakeholder"],
    "Process Improvement": ["process improvement", "process optimization", "process optimisation"],
    "Financial Analysis": ["financial analysis", "financial modeling", "financial modelling", "variance analysis", "budgeting"],
    "Sales Analysis": ["sales analysis", "sales reporting", "sales mis", "sales data"],
    "Inventory Management": ["inventory management", "inventory"],
    "Supply Chain": ["supply chain", "logistics"],
    "Retail Analytics": ["retail analytics", "retail mis", "retail"],
    "Hospitality": ["hospitality", "hotel"],
    "CRM": ["crm", "salesforce", "zoho"],
    "ERP": ["erp", "sap", "tally", "oracle erp"],
    "JIRA": ["jira"],
    "Agile": ["agile", "scrum"],
    "Communication": ["communication skills", "written communication", "verbal communication", "communication"],
    "Attention to Detail": ["attention to detail", "detail-oriented", "detail oriented"],
    "Problem Solving": ["problem solving", "problem-solving"],
    "Team Collaboration": ["cross-functional", "cross functional", "teamwork", "team player"],
}

# practice areas / domains, as opposed to tools. Used to write natural sentences
# ("experience in MIS reporting ... working with Power BI and SQL").
AREA_SKILLS = {"MIS Reporting", "Management Reporting", "Dashboard Development", "Reporting Automation", "Data Validation",
               "Data Analysis", "Data Cleaning", "Data Visualization", "KPI Tracking", "Business Analysis",
               "Requirement Gathering", "Stakeholder Management", "Process Improvement", "Financial Analysis",
               "Sales Analysis", "Inventory Management", "Supply Chain", "Retail Analytics", "Hospitality", "Forecasting",
               "Statistics", "Machine Learning", "Data Modeling", "Data Warehousing", "ETL", "A/B Testing", "Agile",
               "Communication", "Attention to Detail", "Problem Solving", "Team Collaboration"}

# more specific skill implies the generic one (for coverage), never the other way round
IMPLIES = {"Advanced Excel": ["Excel"], "Power Query": ["Excel"], "Power Pivot": ["Excel"], "VBA/Macros": ["Excel"],
           "VLOOKUP/XLOOKUP": ["Excel"], "Pivot Tables": ["Excel"], "DAX": ["Power BI"], "Pandas": ["Python"],
           "MIS Reporting": ["Management Reporting"]}

_ALIAS_INDEX = sorted(((a, canon) for canon, aliases in SKILL_VOCAB.items() for a in aliases), key=lambda x: -len(x[0]))
_ALIAS_RE = re.compile("|".join(rf"(?<![\w+#/]){re.escape(a)}(?![\w+#])" for a, _ in _ALIAS_INDEX), re.I)
_ALIAS_TO_CANON = {a: c for a, c in _ALIAS_INDEX}


def find_skills(text: str) -> set[str]:
    """Canonical skills in text. Longest alias wins, so "Power Pivot" is not also read as "Pivot Tables"."""
    # the alternation is ordered longest-first, and finditer never returns overlapping matches
    return {_ALIAS_TO_CANON[m.group(0).lower()] for m in _ALIAS_RE.finditer(text or "")
            if m.group(0).lower() in _ALIAS_TO_CANON}


def canonical_skill(name: str) -> str:
    """Map a free-text skill ("MS-Excel", "powerbi") to its canonical name when known."""
    key = name.strip().lower()
    if key in _ALIAS_TO_CANON:
        return _ALIAS_TO_CANON[key]
    for canon in SKILL_VOCAB:
        if canon.lower() == key:
            return canon
    m = _ALIAS_RE.search(name or "")
    if m and len(m.group(0)) >= len(key) * 0.6:
        return _ALIAS_TO_CANON.get(m.group(0).lower(), name.strip())
    return name.strip()


def expand_implied(skills: set[str]) -> set[str]:
    out = set(skills)
    for s in skills:
        out.update(IMPLIES.get(s, []))
    return out


# ---------------------------------------------------------------- roles

ROLE_CATEGORIES: dict[str, list[str]] = {
    "Data Analyst": ["data analyst", "data analytics", "analytics analyst", "junior analyst", "data specialist", "analyst - data"],
    "Business Analyst": ["business analyst", "business analysis", "functional analyst", "ba "],
    "BI Analyst": ["bi analyst", "business intelligence", "power bi developer", "bi developer", "tableau developer", "bi engineer"],
    "MIS Executive": ["mis executive", "mis analyst", "mis coordinator", "mis manager", "mis specialist", "mis officer", "mis"],
    "Reporting Analyst": ["reporting analyst", "report analyst", "reporting specialist", "reporting executive", "reporting associate"],
    "Data Scientist": ["data scientist", "machine learning", "ml engineer"],
    "Operations Analyst": ["operations analyst", "ops analyst", "operations executive", "process analyst"],
    "Financial Analyst": ["financial analyst", "finance analyst", "fp&a"],
}

_ROLE_PATTERNS = {cat: re.compile("|".join(rf"\b{re.escape(a.strip())}\b" for a in aliases), re.I)
                  for cat, aliases in ROLE_CATEGORIES.items()}


def role_category(title: str) -> str:
    for cat, pat in _ROLE_PATTERNS.items():
        if pat.search(title or ""):
            return cat
    return "Other"


# words that carry no role meaning when comparing titles
TITLE_NOISE = {"senior", "sr", "junior", "jr", "lead", "associate", "executive", "specialist", "i", "ii", "iii",
               "the", "and", "of", "for", "with", "in", "to", "a", "an", "-", "&", "remote", "hybrid", "trainee"}

ROLE_SYNONYMS = {"bi": "business intelligence", "mis": "management information", "ba": "business analyst",
                 "analytics": "analyst", "analysis": "analyst", "reporting": "report", "reports": "report"}


def title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z]+", (title or "").lower())
    out = set()
    for w in words:
        if w in TITLE_NOISE:
            continue
        w = ROLE_SYNONYMS.get(w, w)
        out.update(w.split())
    return out


# ---------------------------------------------------------------- keywords

STOPWORDS = set("""a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her here
hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once
only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves
then there these they this those through to too under until up very was we were what when where which while who whom why
will with you your yours yourself yourselves etc eg ie via per within across also well must able ability strong good
excellent candidate candidates role job position company team work working experience years year required requirements
responsibilities responsibility preferred including include includes using use used knowledge skills skill understanding
looking join opportunity apply new make ensure based like plus other others day days time full part-time full-time""".split())


def jd_keywords(text: str, limit: int = 30) -> list[str]:
    """Important JD keywords: known skills first, then repeated meaningful words/phrases."""
    skills = sorted(find_skills(text))
    words = [w for w in re.findall(r"[a-z][a-z+#./-]{2,}", (text or "").lower()) if w not in STOPWORDS]
    bigrams = [f"{a} {b}" for a, b in zip(words, words[1:]) if a != b]
    counts = Counter(words) + Counter(b for b in bigrams)
    skill_aliases = {a for aliases in SKILL_VOCAB.values() for a in aliases}
    extra = [w for w, n in counts.most_common(200) if n >= 2 and w not in skill_aliases and not w.isdigit()]
    # drop single words already covered by a chosen bigram
    chosen: list[str] = []
    for w in extra:
        if any(w in c.split() for c in chosen if " " in c):
            continue
        chosen.append(w)
    return (skills + chosen)[:limit]


def contains_keyword(text: str, keyword: str) -> bool:
    if keyword in SKILL_VOCAB:
        return keyword in find_skills(text)
    return re.search(rf"(?<![\w]){re.escape(keyword.lower())}(?![\w])", (text or "").lower()) is not None


ACTION_VERBS = {
    "achieved", "analysed", "analyzed", "automated", "built", "collaborated", "compiled", "consolidated", "coordinated",
    "created", "cut", "delivered", "designed", "developed", "drove", "enhanced", "established", "evaluated", "executed",
    "generated", "identified", "implemented", "improved", "increased", "introduced", "led", "maintained", "managed",
    "monitored", "optimised", "optimized", "organised", "organized", "performed", "prepared", "presented", "produced",
    "reconciled", "reduced", "resolved", "reviewed", "saved", "standardised", "standardized", "streamlined",
    "supported", "tracked", "trained", "transformed", "validated", "verified", "wrote", "reported", "migrated",
    "handled", "ensured", "conducted", "cleaned", "merged", "deployed", "forecast", "forecasted", "modelled", "modeled",
    "extracted", "processed", "updated", "assisted", "provided", "helped", "worked",
}
WEAK_STARTS = {"responsible for", "worked on", "helped with", "involved in", "duties included", "tasked with",
               "in charge of", "assisted in", "handled the"}
