# Reddit Bot – M1 + M2

Reddit ingestion, storage, AI classification, and weekly report.

## Project structure

- **`main.py`** – Entrypoint for **one** controlled run: collection → classification → retention, then **exits**. It refuses to run unless `RUN_PIPELINE=true`.
- **`utils/`** – `config.py` (loads `.env` from project root) and `pipeline_control.py` (run flag + OpenAI budget checks).
- **`data/`** – `db.py`, `rss_fetcher.py`, `reddit_client.py`, `schema.sql` (posts table).
- **`jobs/`** – `run_collection.py`, `run_classification.py`, `run_retention.py`, `weekly_report.py`, `classifier.py`.
- **`scripts/`** – Test scripts (collection, classification, retention, weekly report). Test weekly report sends to a fixed test email only; production uses `REPORT_EMAIL_TO` from `.env`.

## Setup

1. Copy `.env.example` to `.env` and fill the required keys. `OPENAI_API_KEY` may be empty while the pipeline is paused. Schedules, batch sizes, cost controls, retention cadence, and weekly-report limits are all env-driven — see `.env.example` and `utils/config.py`.

2. Create a virtualenv and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Production: schedule `python main.py` (cron)**

   Each invocation runs **once** and exits (no `while True`, background worker, or daemon). Use **[Render Cron Jobs](https://render.com/docs/cronjobs)** (Starter+). Default schedule is once every 24 hours: **`0 9 * * *`**. The process does no work unless `RUN_PIPELINE=true`; leave it `false` when paused.

   Weekly email is handled inside `main.py` on Mondays (UTC), and guarded so only one send happens per ISO week even if Monday has multiple cron ticks. See `REDDIT_APP_SETUP.md`.

**Weekly report (memory-safe):** Counts and breakdowns from SQL; compact JSON attachment. Window and sample caps use `WEEKLY_REPORT_*` env vars.

**Classification:** Batch size is the lower of `CLASSIFICATION_BATCH_SIZE` and `OPENAI_MAX_RECORDS_PER_RUN`; all record caps must be <= 200. Historical/backlog classification is blocked by default: only posts inside `PROCESSING_WINDOW_DAYS` are eligible unless `ALLOW_HISTORICAL_REPROCESSING=true`. Before any OpenAI calls, the job estimates cost from `OPENAI_ESTIMATED_COST_PER_RECORD_USD`, blocks if `OPENAI_RUN_BUDGET_USD` or `OPENAI_WEEKLY_BUDGET_USD` would be exceeded, and records estimated weekly spend in `job_state`.

**RSS collection (streaming):** One feed at a time → insert in chunks of `PIPELINE_MAX_BATCH` → next feed. Pauses and HTTP retry policy come from `RSS_DELAY_BETWEEN_FEEDS_SEC`, `RSS_HTTP_MAX_RETRIES`, and `RSS_HTTP_RETRY_BASE_SEC`; set `RSS_HTTP_MAX_RETRIES=1` for no retry after the first attempt. **Post body** is stored as returned by the feed (no truncation at insert).

**RSS HTTP 429 on Render:** Set a **unique** `RSS_USER_AGENT` in `.env` ([Reddit API wiki](https://github.com/reddit-archive/reddit/wiki/api)). If 429 persists, shorten `SUBREDDIT_LIST` or use explicit `RSS_FEED_URLS`, or switch to **`USE_RSS=false`** with real Reddit OAuth credentials (replace `unused` placeholders for `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`).

See `PIPELINE_CONTROLS.md` for the OpenAI call audit, guarded entrypoints, and backlog controls.

## Running jobs manually

From the `reddit-bot` directory:

| Command | Purpose |
|--------|---------|
| `python -m jobs.run_collection` | One collection cycle, then exits |
| `python -m jobs.run_classification` | Classify unclassified posts (batch) |
| `python -m jobs.run_retention` | Delete posts older than `RETENTION_DAYS` (from `.env`) |
| `python -m jobs.weekly_report` | Build summary for `WEEKLY_REPORT_DAYS` and email to `REPORT_EMAIL_TO` |

All commands above require `RUN_PIPELINE=true`; otherwise they fail closed before doing work.

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
