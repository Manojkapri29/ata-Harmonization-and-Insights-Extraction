"""Your master profile: one YAML file with everything true about you.
Resumes are built from it by selecting and re-ordering - never by inventing."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "profile.yaml"          # your real profile (git-ignored)
EXAMPLE_PATH = ROOT / "profile.example.yaml"  # template committed to the repo


def load_profile(path: Path | None = None) -> dict:
    path = path or (PROFILE_PATH if PROFILE_PATH.exists() else EXAMPLE_PATH)
    return parse_profile(Path(path).read_text(encoding="utf-8"))


def parse_profile(text: str) -> dict:
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("Profile must be a YAML mapping (key: value).")
    for key in ("experience", "projects", "education", "certifications", "target_roles"):
        data.setdefault(key, [])
    data.setdefault("skills", {})
    data.setdefault("contact", {})
    return data


def save_profile(text: str, path: Path | None = None) -> dict:
    data = parse_profile(text)  # validate before writing
    Path(path or PROFILE_PATH).write_text(text, encoding="utf-8")
    return data


def profile_skills(profile: dict) -> list[str]:
    skills = profile.get("skills") or {}
    if isinstance(skills, dict):
        return [s for group in skills.values() for s in (group or [])]
    return list(skills)


def profile_text(profile: dict) -> str:
    parts = [profile.get("headline", ""), profile.get("summary", ""), " ".join(profile_skills(profile))]
    for e in profile.get("experience", []):
        parts += [e.get("title", ""), e.get("company", ""), *e.get("bullets", [])]
    for p in profile.get("projects", []):
        parts += [p.get("name", ""), " ".join(p.get("tech", [])), *p.get("bullets", [])]
    for ed in profile.get("education", []):
        parts.append(ed.get("degree", ""))
    parts += profile.get("certifications", [])
    return "\n".join(str(p) for p in parts if p)
