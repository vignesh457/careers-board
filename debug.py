"""
debug.py

Diagnostic helper for when a source returns 0 (or fewer than expected)
matching roles and you're not sure why. Scrapes ONE source exactly as
run.py would, but shows every candidate link BEFORE filtering, with a
pass/fail flag for each filter stage — so you can see directly whether
the problem is the URL, js_rendered, a stale wait_selector, or your
keyword list, instead of guessing.

Usage:
  python debug.py "Company Name"
  python debug.py "Company Name" --limit 50
"""

import argparse
import json
import sys

from filters import matches_filter, matches_location
from scraper import scrape_source


def main():
    parser = argparse.ArgumentParser(description="Debug why a source returns 0 (or few) results.")
    parser.add_argument("name", help="Exact \"name\" value from sources.json")
    parser.add_argument("--limit", type=int, default=30, help="Max candidate links to print (default 30)")
    args = parser.parse_args()

    with open("sources.json", encoding="utf-8") as f:
        sources = json.load(f)

    matching = [s for s in sources if s["name"] == args.name]
    if not matching:
        available = [s["name"] for s in sources]
        print(f"No source named '{args.name}' in sources.json.")
        print(f"Available: {available}")
        sys.exit(1)

    source = matching[0]
    print(f"Scraping '{source['name']}' -> {source['url']}")
    print(f"  js_rendered={source.get('js_rendered', False)}  "
          f"wait_selector={source.get('wait_selector')!r}  "
          f"require_india_location={source.get('require_india_location', False)}")
    print()

    jobs = scrape_source(source)
    print(f"Found {len(jobs)} raw candidate link(s) on the page. Showing up to {args.limit}:\n")

    keyword_pass = 0
    location_pass = 0
    for j in jobs[: args.limit]:
        kw_ok = matches_filter(j["title"])
        loc_ok = matches_location(j["location"])
        if kw_ok:
            keyword_pass += 1
        if loc_ok:
            location_pass += 1
        kw_flag = "KEYWORD-OK " if kw_ok else "keyword-no "
        loc_flag = "LOCATION-OK" if loc_ok else "location-no"
        print(f"  [{kw_flag}][{loc_flag}] {j['title']!r}")
        print(f"      location={j['location']!r}  url={j['url']}")

    if len(jobs) > args.limit:
        print(f"\n  ...and {len(jobs) - args.limit} more (use --limit to see more)")

    print()
    print(f"Summary: {keyword_pass}/{len(jobs)} passed the keyword filter, "
          f"{location_pass}/{len(jobs)} would pass the location filter (only matters if "
          f"require_india_location is true for this source).")

    if len(jobs) == 0:
        print("\nZero candidate links found at all. Likely causes:")
        print("  1. The page is JS-rendered and js_rendered isn't set to true — check view-source")
        print("     (search for text you can see on the live page; if it's not in the raw HTML,")
        print("     it's JS-rendered).")
        print("  2. The URL is wrong, blocked, or requires a login.")
    elif keyword_pass == 0:
        print("\nLinks were found, but none matched a keyword in settings.json. Likely causes:")
        print("  1. This URL is a landing/category/marketing page, not an actual job LISTING page —")
        print("     open it in a browser and confirm you can see individual job titles, not just")
        print("     category names or descriptive text.")
        print("  2. The page is JS-rendered (job titles load in after page load) and js_rendered")
        print("     isn't set to true, or the wait wasn't long enough for this specific site.")
        print("  3. Your keywords in settings.json genuinely don't match this site's job title")
        print("     wording — check a few of the titles printed above by hand.")


if __name__ == "__main__":
    main()
