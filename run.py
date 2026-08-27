"""
run.py

Reads sources.json, scrapes each career page, filters for relevant/India
postings, and:
  - regenerates data/board.md (persistent, checkable application list)
  - regenerates docs/data.json (feeds the GitHub Pages dashboard)
  - appends new matches to data/new_jobs.md (running history log)
  - optionally sends a Telegram notification

Run:
  python run.py
"""

import json
import os
import re
from datetime import datetime, timezone

from filters import matches_filter, matches_location, is_fresh
from scraper import scrape_source

SOURCES_FILE = "sources.json"
SEEN_FILE = "data/seen_jobs.json"
OUTPUT_FILE = "data/new_jobs.md"
BOARD_FILE = "data/board.md"
DASHBOARD_DATA_FILE = "docs/data.json"


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            return json.load(f)
    return default


def save_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


_BOARD_LINE_RE = re.compile(r"^- \[(x| )\] .*<!-- id:(\S+) -->\s*$")


def read_checked_ids(path: str) -> set:
    """Parses a previously-generated board.md for checked-off job ids, so
    regenerating the board doesn't lose your progress. Tolerant of
    encoding issues in a manually-edited file."""
    checked = set()
    if not os.path.exists(path):
        return checked
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _BOARD_LINE_RE.match(line.rstrip("\n"))
            if m and m.group(1) == "x":
                checked.add(m.group(2))
    return checked


def write_board(path: str, jobs: list):
    checked = read_checked_ids(path)

    def sort_key(j):
        return (j.get("posted_date") or "0000-00-00", j["company"].lower())

    jobs_sorted = sorted(jobs, key=sort_key, reverse=True)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Career Page Job Board\n\n")
        f.write(f"_Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
                f"— {len(jobs_sorted)} open matching roles_\n\n")
        f.write("Tick a box after you apply — your progress is preserved across runs.\n\n")
        for j in jobs_sorted:
            box = "x" if j["id"] in checked else " "
            loc = f" · {j['location']}" if j["location"] else ""
            posted = f" · posted {j['posted_date']}" if j.get("posted_date") else " · date unknown"
            f.write(
                f"- [{box}] **{j['company']}** — [{j['title']}]({j['url']}){loc}{posted} "
                f"<!-- id:{j['id']} -->\n"
            )
    return checked


def write_dashboard_data(path: str, jobs: list, new_ids: set, applied_ids: set):
    def sort_key(j):
        return j.get("posted_date") or "0000-00-00"

    jobs_sorted = sorted(jobs, key=sort_key, reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "jobs": [
            {
                "id": j["id"],
                "company": j["company"],
                "title": j["title"],
                "location": j["location"],
                "url": j["url"],
                "posted_date": j.get("posted_date", ""),
                "is_new": j["id"] in new_ids,
                "applied": j["id"] in applied_ids,
            }
            for j in jobs_sorted
        ],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def notify_telegram(new_jobs):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (bot_token and chat_id) or not new_jobs:
        return
    import requests

    by_company = {}
    for j in new_jobs:
        by_company.setdefault(j["company"], []).append(j)

    header = f"🎯 <b>{len(new_jobs)} new role(s) from career pages</b>\n"
    chunk = header
    for company, jobs in sorted(by_company.items()):
        block = f"\n<b>{company}</b>\n" + "\n".join(
            f"• <a href=\"{j['url']}\">{j['title']}</a> — {j['location'] or 'location n/a'}"
            for j in jobs
        ) + "\n"
        if len(chunk) + len(block) > 3800:
            _send_telegram(bot_token, chat_id, chunk)
            chunk = block
        else:
            chunk += block
    if chunk.strip():
        _send_telegram(bot_token, chat_id, chunk)


def _send_telegram(bot_token, chat_id, text):
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram notify failed: {e}")


def main():
    sources = load_json(SOURCES_FILE, [])
    if not sources:
        print(f"No sources in {SOURCES_FILE} — add at least one entry. See README.md and sources.example.json.")
        return

    seen = set(load_json(SEEN_FILE, []))
    all_current_ids = set()
    new_jobs = []
    all_open_matches = []

    print(f"Scraping {len(sources)} source(s)...")
    for source in sources:
        require_location = source.get("require_india_location", False)
        jobs = scrape_source(source)
        print(f"  {source['name']}: found {len(jobs)} candidate link(s)")

        for j in jobs:
            all_current_ids.add(j["id"])
            location_ok = matches_location(j["location"]) if require_location else True
            if not (matches_filter(j["title"]) and location_ok and is_fresh(j.get("posted_date", ""))):
                continue
            full_job = {**j, "company": source["name"]}
            all_open_matches.append(full_job)
            if j["id"] not in seen:
                new_jobs.append(full_job)

    save_json(SEEN_FILE, sorted(all_current_ids))
    applied_ids = write_board(BOARD_FILE, all_open_matches)
    new_ids = {j["id"] for j in new_jobs}
    write_dashboard_data(DASHBOARD_DATA_FILE, all_open_matches, new_ids, applied_ids)

    if new_jobs:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — {len(new_jobs)} new matching roles\n\n")
            for j in new_jobs:
                loc = f" ({j['location']})" if j["location"] else ""
                f.write(f"- **{j['company']}** — [{j['title']}]({j['url']}){loc}\n")

    print(f"\nDone: {len(all_open_matches)} open matching roles, {len(new_jobs)} new since last run.")
    print(f"  -> {BOARD_FILE}")
    print(f"  -> {DASHBOARD_DATA_FILE}")

    notify_telegram(new_jobs)


if __name__ == "__main__":
    main()
