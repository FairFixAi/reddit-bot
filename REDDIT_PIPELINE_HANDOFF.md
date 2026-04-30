# Reddit Pipeline Handoff

Hi Alan,

Confirmed. I reviewed the current Reddit pipeline codebase and prepared the handoff below for integration into the unified intelligence system.

Current status: the pipeline is paused. `RUN_PIPELINE` is not set in the local `.env`, and the code defaults missing `RUN_PIPELINE` to `false`, so execution fails closed. Please keep `RUN_PIPELINE=false` and do not run the pipeline until further notice.

## 1. Data Output Structure

Current storage is split across two PostgreSQL/Supabase tables:

- `posts`: raw Reddit records
- `post_classifications`: one AI classification row per post

Recommended unified export shape:

```json
{
  "post_id": "native Reddit/RSS external id or Reddit URL",
  "internal_id": 123,
  "source": "reddit_rss",
  "subreddit": "mechanicadvice",
  "title": "Post title",
  "content": "Post body/content as stored",
  "comments": null,
  "timestamp": "2026-04-22T19:46:13+00:00",
  "url": "https://www.reddit.com/r/...",
  "problem_type": "engine",
  "problem_category": "engine",
  "intent": "research",
  "sentiment": "negative",
  "emotional_intensity": 5,
  "financial_mention": false,
  "financial_amount": null,
  "topic": "Automotive Repair",
  "vehicle_make": "Honda",
  "vehicle_model": "CRV",
  "keywords": ["misfire", "spark plugs"],
  "summary": "Short model-generated summary.",
  "suggested_action": "reddit_reply",
  "classified_at": "2026-04-22T20:01:00+00:00"
}
```

Notes:

- `comments` are not currently collected or stored by this pipeline.
- `content` is currently stored as returned by Reddit RSS/API. RSS records may contain HTML markup.
- `problem_type` is not a physical DB column. The current equivalent is `problem_category`; the sample export maps `problem_type` to `problem_category` for integration compatibility.
- A 75-record classified sample export is included in `reddit_pipeline_sample_75.json`.

Current live DB counts from read-only verification:

- `posts`: 579
- `post_classifications`: 534

## 2. Classification Fields

The classifier currently produces:

- `topic`
- `sentiment`
- `emotional_intensity`
- `financial_mention`
- `financial_amount`
- `problem_category`
- `intent`
- `vehicle_make`
- `vehicle_model`
- `keywords`
- `summary`
- `suggested_action`

Requested field mapping:

- `problem_type`: use `problem_category`
- `intent`: already supported
- `sentiment`: already supported
- `emotional_intensity`: already supported, integer 1-10
- `financial_mention / cost detection`: supported through `financial_mention` and `financial_amount`

Allowed classifier values in code:

- `topic`: `Automotive Repair`, `General Question`, `Comparison`, `Other`
- `sentiment`: `positive`, `neutral`, `negative`
- `intent`: `urgent`, `research`, `comparison`, `buying`
- `problem_category`: `engine`, `transmission`, `brakes`, `overheating`, `electrical`, `suspension`, `other`
- `suggested_action`: `google_ads`, `landing_page`, `reddit_reply`, `blog_content`, `none`

## 3. Execution and Entry Points

Production command:

```bash
python main.py
```

Production behavior:

- `main.py` runs one cycle: collection, classification, retention, optional weekly report.
- The process exits after the single run.
- It refuses to do any work unless `RUN_PIPELINE=true`.

Manual guarded commands:

```bash
python -m jobs.run_collection
python -m jobs.run_classification
python -m jobs.run_retention
python -m jobs.weekly_report
```

Test/debug guarded commands:

```bash
python -m scripts.test_collection
python -m scripts.test_classification
python -m scripts.test_retention
python -m scripts.test_weekly_report
```

Deployment entry point:

- `render.yaml`
- Service type: Render Cron Job
- Schedule: `0 9 * * *`
- Start command: `python main.py`

Confirmation:

- No `while True` pipeline loop exists.
- No daemon worker exists.
- No web framework endpoint exists.
- No queue consumer exists.
- No in-repo background scheduler exists.
- The only scheduler reference is external infrastructure through `render.yaml` as a Render cron job.

## 4. Code and Processing Logic

Confirmed branch:

- Branch: `main`
- Remote: `https://github.com/developer-vic/REDDIT_PROJECT.git`
- Latest local commit: `10769b6 open-ai usage control`

Important files:

- Main production entry point: `main.py`
- Collection job: `jobs/run_collection.py`
- Classification job: `jobs/run_classification.py`
- OpenAI classifier call: `jobs/classifier.py`
- DB writes, dedupe, schema helpers: `data/db.py`
- Run flag and OpenAI budget controls: `utils/pipeline_control.py`
- Env/config limits: `utils/config.py`
- DB schema: `data/schema.sql`
- Deployment cron config: `render.yaml`

OpenAI classifier call:

- Location: `jobs/classifier.py`
- Function: `classify_post`
- Model currently used: `gpt-4o-mini`
- SDK retries are disabled with `max_retries=0`.

Deduplication logic:

- Raw post dedupe:
  - DB constraint: `posts(source, external_id)` unique
  - Insert behavior: `ON CONFLICT (source, external_id) DO NOTHING`
  - Location: `data/schema.sql`, `data/db.py`
- Classification dedupe:
  - DB constraint: `post_classifications(post_id)` unique
  - Insert behavior: upsert on `post_id`
  - Location: `data/schema.sql`, `data/db.py`
- Classification selection:
  - Only posts without an existing classification row are selected.
  - Location: `data/db.py`, `get_unclassified_posts`

Budget control logic:

- Location: `utils/pipeline_control.py`
- `ensure_pipeline_enabled()` blocks all guarded commands unless `RUN_PIPELINE=true`.
- `check_openai_budget()` blocks classification if per-run or weekly OpenAI budget would be exceeded.
- `record_openai_estimated_spend()` records estimated spend by ISO week in `public.job_state`.
- Effective classification batch size is `min(CLASSIFICATION_BATCH_SIZE, OPENAI_MAX_RECORDS_PER_RUN)`.
- All major record caps are hard-limited to `<= 200` by `utils/config.py`.

## 5. Data Storage

Current storage:

- PostgreSQL/Supabase via `DATABASE_URL`
- Schema file: `data/schema.sql`

Tables:

```sql
public.posts (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  subreddit TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  selftext TEXT NOT NULL DEFAULT '',
  author TEXT,
  post_url TEXT,
  created_utc TIMESTAMPTZ NOT NULL,
  UNIQUE (source, external_id)
)
```

```sql
public.post_classifications (
  id BIGSERIAL PRIMARY KEY,
  post_id BIGINT NOT NULL REFERENCES public.posts(id) ON DELETE CASCADE,
  topic TEXT,
  sentiment TEXT,
  emotional_intensity INTEGER,
  financial_mention BOOLEAN,
  financial_amount TEXT,
  problem_category TEXT,
  intent TEXT,
  vehicle_make TEXT,
  vehicle_model TEXT,
  keywords TEXT[],
  summary TEXT,
  suggested_action TEXT,
  classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (post_id)
)
```

```sql
public.job_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

Write/update behavior:

- Collection inserts into `posts`.
- Duplicate posts are skipped with `ON CONFLICT DO NOTHING`.
- Classification inserts or updates one row per post in `post_classifications`.
- Retention deletes old rows from `posts`; related classifications are deleted through `ON DELETE CASCADE`.
- Weekly report and OpenAI spend state are stored in `job_state`.

## 6. Integration Readiness

Dependencies:

```bash
pip install -r requirements.txt
```

Current Python package requirements:

- `praw`
- `feedparser`
- `psycopg2-binary`
- `python-dotenv`
- `openai`
- `requests`

Required environment/config:

- `DATABASE_URL`
- `USE_RSS`
- `SUBREDDIT_LIST`
- `RSS_FEED_URLS`
- `FETCH_INTERVAL_MINUTES`
- `CLASSIFICATION_INTERVAL_MINUTES`
- `RETENTION_DAYS`
- `POSTS_PER_RUN`
- `PIPELINE_MAX_BATCH`
- `RSS_MAX_POSTS_PER_RUN`
- `RSS_DELAY_BETWEEN_FEEDS_SEC`
- `CLASSIFICATION_BATCH_SIZE`
- `OPENAI_API_KEY`
- OpenAI budget variables should be set before classification:
  - `OPENAI_MAX_RECORDS_PER_RUN`
  - `OPENAI_RUN_BUDGET_USD`
  - `OPENAI_WEEKLY_BUDGET_USD`
  - `OPENAI_ESTIMATED_COST_PER_RECORD_USD`
- SMTP/report variables are required by config if weekly reports are used.
- Reddit API credentials are optional when `USE_RSS=true`; the code supports `unused` placeholders.

Current ingestion mode:

- Local `.env` has `USE_RSS=true`.
- `RSS_FEED_URLS=DERIVE_FROM_SUBREDDIT_LIST`.
- Current subreddit list includes automotive and car-buying/legal-adjacent subreddits.

Limitations and assumptions:

- Comments are not currently ingested.
- RSS content may include HTML and embedded Reddit feed markup.
- The system is Reddit-specific today; integration should normalize into the unified intelligence schema outside this repo or through a shared processing layer.
- Classification is single-post classification, not conversation/thread-level classification.
- `RUN_PIPELINE` must remain false until an approved run.
- Local `.env` does not explicitly set `RUN_PIPELINE`; this is still paused because the code default is false.
- Local `.env` also does not explicitly set OpenAI run/weekly budget variables, so classification is additionally blocked unless those are configured with positive values.

Thanks,
Victor
