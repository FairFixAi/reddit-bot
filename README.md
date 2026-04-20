# Reddit Bot – M1 + M2

Reddit ingestion, storage, AI classification, and weekly report.

## Project structure

- **`main.py`** – Entrypoint. Run this on the server; it runs collection, classification, retention, and weekly report on schedule.
- **`utils/`** – `config.py` (loads `.env` from project root).
- **`data/`** – `db.py`, `rss_fetcher.py`, `reddit_client.py`, `schema.sql` (posts table).
- **`jobs/`** – `run_collection.py`, `run_classification.py`, `run_retention.py`, `weekly_report.py`, `classifier.py`.
- **`scripts/`** – Test scripts (collection, classification, retention, weekly report). Test weekly report sends to a fixed test email only; production uses `REPORT_EMAIL_TO` from `.env`.

## Setup

1. Copy `.env.example` to `.env` and fill in at least:
   - `DATABASE_URL` (Supabase/PostgreSQL)
   - `SUBREDDIT_LIST` or `RSS_FEED_URLS` (or use defaults)
   - For M2: `OPENAI_API_KEY`, `REPORT_EMAIL_TO`, `SMTP_USER`, `SMTP_PASSWORD`

2. Create a virtualenv and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Production: run once on the server**

   ```bash
   python main.py
   ```

   This runs indefinitely and, on schedule:
   - **Collection** every `FETCH_INTERVAL_MINUTES` (default 5)
   - **Classification** every `CLASSIFICATION_INTERVAL_MINUTES` (default 60)
   - **Retention** once per day (deletes posts older than `RETENTION_DAYS`)
   - **Weekly report** once per week (email + JSON to `REPORT_EMAIL_TO`)

**Weekly report (memory-safe):** The job builds counts and breakdowns in the database and only loads capped samples (no full-window `selftext` load). The JSON attachment is a compact summary. A full export of every raw post for the window is **not** included by default (keeps small Render workers stable). To attach the legacy full `posts` array, set `WEEKLY_REPORT_INCLUDE_FULL_POSTS=true` (not recommended for large datasets).

**Classification:** Each run classifies at most `CLASSIFICATION_BATCH_SIZE` posts (default 25) so the worker does not pull an unbounded unclassified list into memory or call OpenAI for thousands of rows in one tick. Optional: `CLASSIFICATION_MAX_SELFTEXT_CHARS` truncates body text sent to the model only (full text remains in the DB if already stored).

**RSS collection (Render / OOM):** Production collection **does not** accumulate all feeds into one list. It **fetches one feed → inserts to Supabase → releases**, then the next feed, until `RSS_MAX_POSTS_PER_RUN` budget is used. `insert_posts` also **chunks** writes (`INSERT_POSTS_CHUNK_SIZE`, default 25) with a **commit per chunk**. `RSS_MAX_SELFTEXT_CHARS` defaults to **50000** per stored body. Tune `RSS_MAX_POSTS_PER_RUN`, `INSERT_POSTS_CHUNK_SIZE`, and `CLASSIFICATION_BATCH_SIZE` (default **25**) on 512 MB workers.

**RSS HTTP 429 on Render:** Reddit rate-limits repeated requests from cloud IPs. This repo **sleeps `RSS_DELAY_BETWEEN_FEEDS_SEC` (default 3.5s)** between feeds, **retries 429** with backoff and `Retry-After`, and sends **`RSS_USER_AGENT`** (falls back to `REDDIT_USER_AGENT`). On Render, set a **unique** `RSS_USER_AGENT` (see [Reddit API wiki](https://github.com/reddit-archive/reddit/wiki/api)); if 429 persists, raise `RSS_DELAY_BETWEEN_FEEDS_SEC` (e.g. `6`) or shorten `SUBREDDIT_LIST` / use the official Reddit API (`USE_RSS=false`) with OAuth.

**Weekly report:** Leave `WEEKLY_REPORT_INCLUDE_FULL_POSTS` unset or `false` on Render so the job does not load full raw windows into memory.

## Running jobs manually

From the `reddit-bot` directory:

| Command | Purpose |
|--------|---------|
| `python -m jobs.run_collection` | One collection cycle (then exits; or loops if run as script) |
| `python -m jobs.run_classification` | Classify unclassified posts (batch) |
| `python -m jobs.run_retention` | Delete posts older than `RETENTION_DAYS` |
| `python -m jobs.weekly_report` | Build 7-day summary and email to `REPORT_EMAIL_TO` |

## Test scripts (scripts/)

| Command | Purpose |
|--------|---------|
| `python -m scripts.test_collection` | One collection cycle |
| `python -m scripts.test_classification` | Classify up to 2 posts |
| `python -m scripts.test_retention` | Run retention (delete old posts) |
| `python -m scripts.test_weekly_report` | Build and send weekly report to test recipient only (not `REPORT_EMAIL_TO`) |

## Database

**New Supabase project:** run `data/schema.sql` once in **SQL Editor** (creates `posts` and `post_classifications` with indexes). Alternatively, call `data.db.init_schema()` from a one-off script with `DATABASE_URL` set.

**VPS / Linux: `Network is unreachable` to Supabase (often IPv6):** The direct host `db.<project>.supabase.co` may resolve to IPv6; many VPSes have no IPv6 route. In Supabase **Dashboard → Connect → Session pooler**, copy the **IPv4-friendly** URI (host like `aws-0-<region>.pooler.supabase.com`, user `postgres.<project-ref>`, port **5432**). Set that as `DATABASE_URL`. Details: `REDDIT_APP_SETUP.md` (same issue as Render).

- **`posts`** – Raw posts (`source`, `external_id`, `subreddit`, `title`, `selftext`, `author`, `post_url`, `created_utc`). Unique on `(source, external_id)`.
- **`post_classifications`** – One row per post (`topic`, `sentiment`, `emotional_intensity`, `financial_mention`, `financial_amount`, `problem_category`, `intent`, `vehicle_make`, `vehicle_model`, `keywords`, `summary`, `suggested_action`, `classified_at`). Unique on `post_id`; `classified_at` defaults to `NOW()` and is updated on each upsert for weekly windows and trends.
