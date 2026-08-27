"""
scraper.py

Fetches a career page and extracts candidate job links. Extraction is
deliberately unfiltered — filters.matches_filter() (applied by the
caller in run.py) does the job of separating real postings from
nav/footer noise.

Honest limitations:
  - Location is a best-effort guess from text near the link, frequently
    blank.
  - No reliable posting date is available from most listing pages.
  - JS-rendered career pages need "js_rendered": true in sources.json,
    which requires Playwright (optional dependency — see README).
  - Bot-protected sites (Cloudflare challenges, login walls) won't work.
"""

import hashlib
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 CareerScraper/1.0"
)
REQUEST_TIMEOUT = 15
MAX_LINKS_PER_PAGE = 500
LOCATION_HINT_MAX_LEN = 60


def fetch_static(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def fetch_rendered(url: str, wait_selector: str = None, timeout_ms: int = 30000) -> str:
    """Renders a JS-heavy page with a real (headless) browser.

    Deliberately does NOT use wait_until="networkidle" — many real sites
    (Amazon's job search among them) run continuous background analytics/
    polling that never lets the network go idle, so networkidle just times
    out waiting for something that will never happen. domcontentloaded is
    far more reliable; wait_selector (when given) is the actual signal
    that the content you care about has actually rendered.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError as e:
        raise RuntimeError(
            "This source has \"js_rendered\": true but Playwright isn't installed. "
            "Uncomment playwright in requirements.txt, run "
            "'pip install -r requirements.txt && playwright install --with-deps chromium', "
            "or set js_rendered to false for this source. See README."
        ) from e

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=timeout_ms)
                except PlaywrightTimeoutError:
                    # The selector never appeared — often means it's stale
                    # (framework-generated class names change between
                    # deploys) rather than the page being broken. Fall
                    # back to a fixed grace period instead of failing the
                    # whole scrape outright; we still read whatever
                    # rendered.
                    print(f"  [warn] wait_selector '{wait_selector}' never appeared on {url} — "
                          f"falling back to a fixed wait. Consider removing/updating it in sources.json.")
                    page.wait_for_timeout(6000)
            else:
                # No selector given — a fixed grace period so client-side
                # rendering has a moment to run before we read the DOM.
                page.wait_for_timeout(6000)

            html = page.content()
        finally:
            browser.close()
    return html


def parse_job_links(html: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_urls = set()

    for a in soup.find_all("a", href=True)[:MAX_LINKS_PER_PAGE]:
        title = a.get_text(strip=True)
        if not title or len(title) < 4:
            continue

        href = a["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue

        url = urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        location = ""
        parent = a.find_parent(["li", "tr", "div"])
        if parent is not None:
            surrounding = parent.get_text(" ", strip=True)
            location = surrounding.replace(title, "", 1).strip()[:LOCATION_HINT_MAX_LEN]

        results.append({"title": title, "url": url, "location": location})

    return results


def scrape_source(source: dict):
    """source: {"name", "url", "js_rendered" (opt), "wait_selector" (opt),
    "require_india_location" (opt)}

    Returns a list of job dicts: {id, title, location, url, posted_date}.
    posted_date is always "" — see module docstring.
    """
    name = source["name"]
    url = source["url"]
    js_rendered = source.get("js_rendered", False)
    wait_selector = source.get("wait_selector")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "source"

    try:
        html = fetch_rendered(url, wait_selector=wait_selector) if js_rendered else fetch_static(url)
    except Exception as e:
        print(f"  [error] {slug}: {e}")
        return []

    links = parse_job_links(html, url)

    jobs = []
    for link in links:
        job_id = "custom-" + slug + "-" + hashlib.sha1(link["url"].encode("utf-8")).hexdigest()[:16]
        jobs.append({
            "id": job_id,
            "title": link["title"],
            "location": link["location"],
            "url": link["url"],
            "posted_date": "",
        })
    return jobs
