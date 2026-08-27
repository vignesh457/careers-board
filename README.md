# Career Page Job Board

Tracks job postings from any company's careers page — no ATS API needed.
Add a URL, it scrapes daily, and matching roles show up on a clean
dashboard you can check off as you apply.

Same deployment pattern as a GitHub-based job tracker: plain Python +
GitHub Actions (schedule) + GitHub Pages (dashboard). No server to host,
no database, nothing to pay for.

## How it works

1. **`sources.json`** — your list of career pages to track. You maintain
   this by hand (see "Adding a source" below).
2. **`run.py`** — fetches each source, extracts every link on the page,
   and keeps only the ones that look like a real job posting (matched
   against `settings.json`'s keyword list). Writes results to:
   - **`data/board.md`** — your actual working list: every currently open
     matching role, as a checklist. Tick a box after you apply — it stays
     ticked across future runs.
   - **`docs/data.json`** — feeds the dashboard (see below).
   - **`data/new_jobs.md`** — a running history log of what was found and
     when.
3. **`docs/index.html`** — a searchable, filterable dashboard reading
   `docs/data.json`, deployed via GitHub Pages.
4. **`.github/workflows/scraper.yml`** — runs `run.py` automatically every
   day at 11:00 AM IST and commits the results back to the repo.

## First-time setup

```bash
pip install -r requirements.txt
```

## Adding a source

Open `sources.json` (starts empty — `[]`) and add an entry. Follow
`sources.example.json` as a template:

```json
[
  {
    "name": "Acme Corp",
    "url": "https://acme.com/careers",
    "require_india_location": false
  }
]
```

**Fields:**
| Field | Required | Default | What it does |
|---|---|---|---|
| `name` | yes | — | Shown on your dashboard and board.md |
| `url` | yes | — | The careers page to scrape |
| `js_rendered` | no | `false` | Set `true` if the page needs JavaScript to show job listings (see below) |
| `wait_selector` | no | none | Only used with `js_rendered: true` — a CSS selector to wait for before reading the page |
| `require_india_location` | no | `false` | Only keep postings where India/a known city is detected near the link. Off by default — see "Getting results in the right way" below for why |

**How to check if a page needs `js_rendered: true`:**
1. Open the careers page in your browser, note a job title you can see.
2. Right-click → "View Page Source" (or visit `view-source:` + the URL).
3. Search (Ctrl+F) for that job title in the source.
   - **Found it** → `js_rendered: false` (default), plain scraping works.
   - **Not found** → `js_rendered: true`, and you'll need the Playwright
     setup below.

**If you need `js_rendered: true`:**
1. In `requirements.txt`, uncomment the `playwright` line.
2. Run:
   ```bash
   pip install -r requirements.txt
   playwright install --with-deps chromium
   ```
3. In `.github/workflows/scraper.yml`, uncomment the "Install Playwright
   browser" step.
4. For `wait_selector`: right-click a job title on the live page →
   Inspect → in dev tools, right-click the highlighted element (or the
   row/card containing it) → Copy → Copy selector → paste that value in.
   If you're not sure, leave it blank — the scraper falls back to a fixed
   6-second wait for the page to render, which works fine for most sites.
   Framework-generated selectors (long chains with hashed class names) are
   often brittle and can break on the site's next deploy — if one stops
   working, it's usually safe to just remove it and rely on the fallback.

## Running it

```bash
python run.py
```

Watch the console output:
```
Scraping 2 source(s)...
  Acme Corp: found 47 candidate link(s)
  Beta Inc: found 12 candidate link(s)

Done: 8 open matching roles, 8 new since last run.
```

- The **first run** will show everything currently open as "new" — that's
  expected, it's establishing the baseline. Later runs only report
  genuinely new postings.
- A `[error] <name>: ...` line means that source failed (bad URL, needs
  `js_rendered: true`, or blocked) — it's skipped for that run without
  affecting the others.
- Check `data/board.md` — this is your real working list.

## Getting results in the correct way (read this before assuming a source is broken)

This is fundamentally different from querying a real API — it's guessing
based on link text on a page. Some things that look like bugs are actually
expected behavior:

- **A source shows 0 matching jobs even though the page clearly has
  openings.** Almost always means the page is JS-rendered — check the
  view-source test above.
- **Location is blank for most/all jobs.** Normal — most career listing
  pages don't show the city until you click into the individual posting.
  This is why `require_india_location` defaults to `false`: you're already
  choosing to track this specific company, so the source itself is the
  vetting step. Turn it on only for a source where you specifically want
  postings dropped when no location text is detected nearby — understand
  that this will also drop genuinely-relevant postings that just don't
  show location on the index page.
- **Dates always say "date unknown."** Expected — this scraper doesn't
  invent a posting date. Freshness is instead judged by whether a job
  disappeared and reappeared as "new" in `data/new_jobs.md`, not by a
  timestamp.
- **A job's title looks like it has location text jammed into it** (e.g.
  "Software Engineer Bengaluru, Karnataka, India"). Some sites put the
  whole thing in one link with no separate location element. It's still a
  real, clickable match — just not as clean-looking as a proper API
  result.
- **Nothing shows up at all, and there's no error.** Check `settings.json`
  — your keyword list might genuinely not match anything on that page. Try
  temporarily adding a very broad keyword (like the company's own name) to
  confirm the scraper is seeing content at all, then narrow back down.

## Debugging a source that returns 0 (or unexpected) results

Don't guess — run the diagnostic tool:

```bash
python debug.py "Company Name"
```

This scrapes just that one source and shows **every** candidate link it
found on the page, before any filtering, with a pass/fail flag for the
keyword filter and location filter next to each one:

```
Scraping 'Amazon' -> https://www.amazon.jobs/en/search?base_query=software&loc_query=Hyderabad,+India
  js_rendered=True  wait_selector=None  require_india_location=False

Found 42 raw candidate link(s) on the page. Showing up to 30:

  [KEYWORD-OK ][LOCATION-OK] 'Software Development Engineer II'
      location='Hyderabad, India'  url=https://www.amazon.jobs/jobs/...
  [keyword-no ][LOCATION-OK] 'Sr. Program Manager'
      location='Hyderabad, India'  url=https://www.amazon.jobs/jobs/...

Summary: 14/42 passed the keyword filter, 42/42 would pass the location filter.
```

This immediately tells you which of these is actually happening:
- **0 candidate links found at all** → the page is JS-rendered and
  `js_rendered` isn't set, or the URL is wrong/blocked.
- **Links found, but they're nav/footer text, not job titles** (e.g.
  "Teams", "Locations", "FAQ") → you're pointed at a landing/marketing
  page, not the actual job search results page. Many companies have
  separate "About this location" pages that look similar to search
  results but contain zero listings — always confirm you're on a page
  where you can see individual job titles when you open it in a real
  browser, not just category names or descriptive text.
- **Real job titles found, but 0 pass the keyword filter** → your
  `settings.json` keywords don't match this site's actual title wording;
  check the titles printed above and adjust.

## Tuning what counts as a match

Edit `settings.json`:
- `keywords` — a job title must contain at least one of these (matched as
  whole words, so `"ui"` won't accidentally match inside another word).
- `exclude_keywords` — a title containing any of these gets dropped even
  if it matched a keyword above (defaults exclude senior/leadership
  titles).
- `location_keywords` — only used for sources with
  `require_india_location: true`.
- `max_posting_age_days` — only relevant for sources that somehow do
  expose a real date; most won't.

Changes take effect on the next `python run.py` — no restart needed since
this isn't a running server.

## Automating with GitHub Actions

1. Push this folder to a GitHub repo.
2. The **Career Page Scraper** workflow runs automatically every day at
   11:00 AM IST and commits results back to `data/` and `docs/data.json`.
   Trigger it manually anytime from the **Actions** tab → **Run workflow**.
3. **Repo permissions**: Settings → Actions → General → Workflow
   permissions → make sure **"Read and write permissions"** is selected,
   or the commit-back step will silently fail.

## Deploying the dashboard (GitHub Pages)

1. Settings → Pages → Source: **Deploy from a branch** → Branch: `main`,
   folder: **`/docs`** → Save.
2. You'll get a URL like `https://<username>.github.io/<repo>/` within a
   minute or two. Bookmark it.
3. Refresh after each daily run to see the current board — search, filter
   by company, sort by newest, click straight through to apply.

**Note:** GitHub Pages on a free personal account only publishes from
**public** repos (a private repo needs GitHub Pro). Job titles and company
names aren't sensitive, so a public repo is usually fine — just don't
commit anything else sensitive into it.

**Checking off applications:** `data/board.md` is the durable record —
check a box there (GitHub app, web UI, or a local edit + push) and it
persists across daily runs, showing as a greyed-out ✓ on the dashboard too.
The dashboard's own checkbox is a device-local shortcut (saved in your
browser only) for quickly marking things while browsing — it won't sync
across devices or back into the repo.

## Optional: Telegram notifications

1. Message **@BotFather** on Telegram → `/newbot` → copy the token.
2. Message your new bot anything, then visit
   `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat.id`.
3. In your repo: Settings → Secrets and variables → Actions → add
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. Next scheduled run will message you when there's something new.

## Limitations, stated plainly

- No structured job schema — this extracts links and guesses, it doesn't
  read a real API.
- JS-rendered pages need Playwright (optional, heavier dependency).
- Bot-protected sites (Cloudflare challenges, login walls) won't work —
  there's no workaround for that here.
- Pagination isn't handled — only what's visible on the initial page load
  gets scraped.
