"""Application tracker stored as a CSV you own (open it in Excel any time)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .profile import ROOT

TRACKER_PATH = ROOT / "data" / "applications.csv"
STATUSES = ["Saved", "Applied", "Screening", "Interview", "Offer", "Rejected", "Withdrawn"]
COLUMNS = ["key", "date_added", "title", "company", "location", "source", "url", "score",
           "status", "applied_on", "follow_up_on", "notes"]


def load(path: Path | None = None) -> pd.DataFrame:
    path = path or TRACKER_PATH
    if Path(path).exists():
        df = pd.read_csv(path, dtype=str).fillna("")
        for col in COLUMNS:
            if col not in df:
                df[col] = ""
        return df[COLUMNS]
    return pd.DataFrame(columns=COLUMNS)


def save(df: pd.DataFrame, path: Path | None = None) -> None:
    path = path or TRACKER_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(path, index=False)


def add(df: pd.DataFrame, job: dict, score: int | str = "", status: str = "Saved") -> tuple[pd.DataFrame, bool]:
    """Add a job unless it is already tracked. Returns (df, added)."""
    if job["key"] in set(df["key"]):
        return df, False
    row = {c: "" for c in COLUMNS}
    row.update({k: str(job.get(k, "")) for k in ("key", "title", "company", "location", "source", "url")})
    row.update(date_added=date.today().isoformat(), score=str(score), status=status)
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True), True


def summary(df: pd.DataFrame) -> dict[str, int]:
    counts = df["status"].value_counts().to_dict() if len(df) else {}
    return {s: int(counts.get(s, 0)) for s in STATUSES}
