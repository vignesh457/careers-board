"""
filters.py

Keyword, location, and freshness filtering — settings are loaded from
settings.json so you can tune them without touching code.
"""

import json
import os
import re
from datetime import datetime, timezone

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "keywords": [
        "frontend", "front end", "backend", "back end", "developer",
        "software engineer", "software developer", "sde",
        "software development engineer", "full stack", "fullstack",
        "full stack developer", "frontend developer", "backend developer",
        "web developer", "application developer", "mern", "react",
        "react developer", "javascript", "typescript", "node", "node developer",
        "java", "java developer", "spring", "spring boot", "ui",
        "ui developer", "ui engineer",
    ],
    "exclude_keywords": [
        "staff", "principal", "director", "manager", "vp ", "head of",
        "architect", "lead ", " sr.", "senior director", "senior staff",
    ],
    "location_keywords": [
        "india", "bangalore", "bengaluru", "hyderabad", "pune", "chennai",
        "mumbai", "delhi", "gurgaon", "gurugram", "noida", "kolkata",
        "ahmedabad", "jaipur", "kochi", "coimbatore", "indore", "chandigarh",
        "nagpur", "gandhinagar", "trivandrum", "thiruvananthapuram",
    ],
    "max_posting_age_days": 30,
    "exclude_senior": True,
}


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            user_settings = json.load(f)
        merged = {**DEFAULT_SETTINGS, **user_settings}
        return merged
    return dict(DEFAULT_SETTINGS)


_settings = load_settings()
_KEYWORD_PATTERNS = [re.compile(r"\b" + re.escape(k) + r"\b") for k in _settings["keywords"]]
_LOCATION_PATTERNS = [re.compile(r"\b" + re.escape(k) + r"\b") for k in _settings["location_keywords"]]


def matches_filter(title: str) -> bool:
    t = " " + title.lower()
    if not any(p.search(t) for p in _KEYWORD_PATTERNS):
        return False
    if _settings.get("exclude_senior", True):
        if any(k in t for k in _settings["exclude_keywords"]):
            return False
    return True


def matches_location(location: str) -> bool:
    if not location:
        return False
    loc = location.lower()
    return any(p.search(loc) for p in _LOCATION_PATTERNS)


def is_fresh(posted_date: str) -> bool:
    max_age = _settings.get("max_posting_age_days", 30)
    if max_age <= 0 or not posted_date:
        return True
    try:
        posted = datetime.strptime(posted_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - posted).days <= max_age
