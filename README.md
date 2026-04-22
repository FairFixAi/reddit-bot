# Reddit Bot – M1 + M2

Reddit ingestion, storage, AI classification, and weekly report.

## Project structure

- **`main.py`** – Entrypoint for **one** run: collection → classification → retention, then **exits**. Schedule it with **Render Cron** (or another scheduler) so each invocation is a fresh process (flat memory). Weekly email is **`python -m jobs.weekly_report`** on its own cron (see `render.yaml`).
- **`utils/`** – `config.py` (loads `.env` from project root).
- **`data/`** – `db.py`, `rss_fetcher.py`, `reddit_client.py`, `schema.sql` (posts table).
- **`jobs/`** – `run_collection.py`, `run_classification.py`, `run_retention.py`, `weekly_report.py`, `classifier.py`.
- **`scripts/`** – Test scripts (collection, classification, retention, weekly report). Test weekly report sends to a fixed test email only; production uses `REPORT_EMAIL_TO` from `.env`.

## Setup

1. Copy `.env.example` to `.env` and fill **every** key (empty values are rejected at import). Schedules, batch sizes, RSS retry policy, retention cadence, and weekly-report limits are all env-driven — see `.env.example` and `utils/config.py`.

2. Create a virtualenv and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Production: schedule `python main.py` (cron)**

   Each invocation runs **once** and exits (no `while True` in `main.py`). Use **[Render Cron Jobs](https://render.com/docs/cronjobs)** (Starter+). Example tick: **`0 */6 * * *`** (every 6 hours) with **`FETCH_INTERVAL_MINUTES=360`** and **`CLASSIFICATION_INTERVAL_MINUTES=360`** in env (`render.yaml` + `.env.example` match that). Set **`PYTHONUNBUFFERED=1`** on Render.

   Add a **second** cron for the weekly email: `python -m jobs.weekly_report` (example: Mondays 09:00 UTC in `render.yaml`). See `REDDIT_APP_SETUP.md`.

**Weekly report (memory-safe):** Counts and breakdowns from SQL; compact JSON attachment. Window and sample caps use `WEEKLY_REPORT_*` env vars.

**Classification:** Batch size is `CLASSIFICATION_BATCH_SIZE`. Full `posts.selftext` is sent to the classifier (see `jobs/classifier.py` for model limits).

**RSS collection (streaming):** One feed at a time → insert in chunks of `PIPELINE_MAX_BATCH` → next feed. Pauses and HTTP retries come from `RSS_DELAY_BETWEEN_FEEDS_SEC`, `RSS_HTTP_MAX_RETRIES`, and `RSS_HTTP_RETRY_BASE_SEC`. **Post body** is stored as returned by the feed (no truncation at insert).

**RSS HTTP 429 on Render:** Set a **unique** `RSS_USER_AGENT` in `.env` ([Reddit API wiki](https://github.com/reddit-archive/reddit/wiki/api)). If 429 persists, shorten `SUBREDDIT_LIST` or use explicit `RSS_FEED_URLS`, or switch to **`USE_RSS=false`** with real Reddit OAuth credentials (replace `unused` placeholders for `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`).

## Running jobs manually

From the `reddit-bot` directory:

| Command | Purpose |
|--------|---------|
| `python -m jobs.run_collection` | One collection cycle, then exits |
| `python -m jobs.run_classification` | Classify unclassified posts (batch) |
| `python -m jobs.run_retention` | Delete posts older than `RETENTION_DAYS` (from `.env`) |
| `python -m jobs.weekly_report` | Build summary for `WEEKLY_REPORT_DAYS` and email to `REPORT_EMAIL_TO` |

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
